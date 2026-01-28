import time
import traceback
import asyncio
import json
import os
import re
import logging
import sys
import signal
from datetime import datetime, timezone
from pathlib import Path

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

# Добавляем корень проекта в sys.path для импорта app модулей
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db_adapter import (
    init_db_pool, close_db_pool, fetch_next_queued_job,
    update_job, refund_credit, get_user_by_tg_id
)
MAX_RETRY_ATTEMPTS = 3  # Максимум попыток для TEMPORARY errors
from app.services.storage_factory import get_storage
from worker.kie_client import create_task_sora_i2v, poll_record_info, KIE_RECORD_INFO_URL
from worker.kie_error_classifier import classify_kie_error, should_retry, get_retry_delay, get_user_error_message, KieErrorType
from worker.kie_key_rotator import get_rotator
from worker.openai_prompter import build_prompt_with_gpt
from worker.prompt_templates import TEMPLATES  # ✅ ВАЖНО

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Флаг для graceful shutdown
shutdown_flag = False

def handle_shutdown(signum, frame):
    global shutdown_flag
    logger.info(f"⚠️ Received signal {signum}, initiating graceful shutdown...")
    shutdown_flag = True


def req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        logger.error(f"❌ Missing env var: {name}")
        raise RuntimeError(f"Missing env var: {name}")
    logger.info(f"✅ Environment variable {name} is set")
    return v.strip()


BOT_TOKEN = req("BOT_TOKEN")
SERVICE_CHANNEL_ID = int(os.getenv("SERVICE_CHANNEL_ID", "0"))  # Optional: for pre-uploading videos


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kb_result(kind: str = "reels") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Сгенерировать ещё", callback_data=f"again:{kind}")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


async def get_public_input_url(input_path: str) -> str:
    """Получить публичный URL для input файла через storage_factory"""
    # Если это уже URL - вернуть как есть
    if input_path and (input_path.startswith("http://") or input_path.startswith("https://")):
        return input_path
    
    try:
        storage = get_storage()
        # Normalize path
        rel = (input_path or "").strip().lstrip("/")
        while rel.startswith("inputs/"):
            rel = rel[len("inputs/"):]
        
        return await storage.get_public_url("inputs", rel)
    except Exception as e:
        logger.error(f"❌ Failed to get public URL for {input_path}: {e}")
        raise


def extract_fail_message(info: dict) -> str | None:
    try:
        data = info.get("data") if isinstance(info, dict) else None
        if isinstance(data, dict):
            state = (data.get("state") or data.get("status") or "").lower()
            if state in {"fail", "failed", "error"}:
                return data.get("failMsg") or data.get("message") or "KIE failed"
    except Exception:
        pass
    return None


def find_video_url(obj):
    common_keys = {
        "video", "video_url", "videoUrl", "output_url", "outputUrl",
        "url", "download_url", "downloadUrl", "file_url", "fileUrl",
        "result_url", "resultUrl", "play_url", "playUrl"
    }

    if obj is None:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in common_keys and isinstance(v, str) and v.startswith("http"):
                return v
        for v in obj.values():
            got = find_video_url(v)
            if got:
                return got
    if isinstance(obj, list):
        for it in obj:
            got = find_video_url(it)
            if got:
                return got
    if isinstance(obj, str):
        m = re.search(r"https?://[^\s\"']+\.(mp4|mov|webm|m3u8)(\?[^\s\"']+)?", obj, re.I)
        if m:
            return m.group(0)
    return None


async def download_bytes(url: str) -> bytes:
    """Скачивает видео с KIE по URL (не сохраняет на диск)"""
    import time
    start_time = time.time()
    
    # Увеличиваем timeout до 300 сек (5 минут) для больших видео
    # Видео могут быть 50-100+ МБ и скачиваться долго
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        
        elapsed = time.time() - start_time
        size_mb = len(r.content) / 1024 / 1024
        speed_mbps = (size_mb / elapsed) if elapsed > 0 else 0
        
        logger.info(f"✅ Downloaded video: {size_mb:.2f} MB in {elapsed:.1f}s ({speed_mbps:.2f} MB/s)")
        return r.content


async def fetch_record_info_once(task_id: str, api_key: str) -> dict:
    """Делает один запрос recordInfo (без долгого poll)."""
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.get(f"{KIE_RECORD_INFO_URL}?taskId={task_id}", headers={"Authorization": f"Bearer {api_key}"})
        r.raise_for_status()
        return r.json()


def build_script_for_job(job: dict) -> str:
    """
    ✅ ВАЖНО: тут выбираем шаблон по job.template_id
    """
    logger.info(f"🔧 Building script for job {job.get('id')}")
    
    # Template_id хранится в error_details JSONB
    error_details = job.get("error_details") or {}
    if isinstance(error_details, str):
        import json
        try:
            error_details = json.loads(error_details)
        except:
            error_details = {}
    
    template_id = error_details.get("template_id") or job.get("template_id") or "ugc"
    template_id = template_id.strip()
    tpl = TEMPLATES.get(template_id) or TEMPLATES.get("ugc")

    # 🔍 DEBUG: Смотрим что есть в job
    logger.info(f"🔍 DEBUG job fields: product_info={job.get('product_info')}, product_text={job.get('product_text')[:100] if job.get('product_text') else None}, prompt={job.get('prompt')[:100] if job.get('prompt') else None}")
    logger.info(f"🔍 DEBUG error_details: {error_details}")
    
    # ИСПРАВЛЕНИЕ: product_info НЕ существует в БД! Читаем из product_text (это JSON)
    product_info_raw = job.get("product_text") or job.get("prompt") or "{}"
    product_info = {}
    
    if isinstance(product_info_raw, str):
        import json
        try:
            product_info = json.loads(product_info_raw)
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse product_text as JSON: {e}, using as plain text")
            # Если не JSON - это просто текст, оборачиваем в dict
            product_info = {"text": product_info_raw}
    elif isinstance(product_info_raw, dict):
        product_info = product_info_raw
    
    product_text = (product_info.get("text") or "").strip()
    
    # 🔍 ЛОГИРУЕМ ЧТО ПРИШЛО ПОЛЬЗОВАТЕЛЕМ
    logger.info(f"🔍 Product info from user: text='{product_text[:500]}{'...' if len(product_text) > 500 else ''}'")
    logger.info(f"🔍 Template selected: {template_id}")
    extra_wishes = job.get("extra_wishes")

    # 🧑‍💻 Сам себе продюсер — GPT НЕ нужен
    if tpl.get("type") == "direct":
        user_prompt = (product_info.get("user_prompt") or "").strip()
        if not user_prompt:
            raise RuntimeError("self_template_missing_user_prompt")
        
        # Добавляем информацию о товаре в кастомный промпт
        # Формат: "... Important: preserve the exact appearance of the product from the photo - {product_text}"
        if product_text:
            user_prompt = f"{user_prompt}\n\nINFO ABOUT PRODUCT: {product_text}\n\nImportant: preserve the exact appearance of the product from the photo - color, shape, size, all details must match."
            logger.info(f"✅ Added product info to custom prompt: {product_text[:100]}...")
        
        return user_prompt

    # GPT → сценарий/промпт
    logger.info(f"📊 Attempting GPT script generation: product='{product_text[:50]}...', template={template_id}")
    try:
        script = build_prompt_with_gpt(
            system=tpl["system"],
            instructions=tpl["instructions"],
            product_text=product_text,
            extra_wishes=extra_wishes,
        )
        logger.info(f"✅ Script built successfully via GPT: {len(script)} chars")
        logger.debug(f"Generated script: {script[:150]}...")
        return script
    except Exception as e:
        logger.error(f"❌ GPT failed (maybe out of tokens?): {repr(e)}", exc_info=True)
        
        # 🔄 FALLBACK: Генерируем базовый хороший промт БЕЗ GPT
        # Важно: это должен быть РЕАЛЬНЫЙ ПРОМТ ДЛЯ SORA, не инструкция для GPT!
        logger.warning(f"⚠️ FALLBACK ACTIVATED: Using simplified prompt instead of GPT")
        logger.warning(f"⚠️ Reason: OpenAI API error ({type(e).__name__}). Check OpenAI credits!")
        
        product_text = product_text or "product"
        extra_wishes_text = f" {extra_wishes}" if extra_wishes else ""
        
        # Простой но эффективный промт для Sora
        fallback_prompt = (
            f"Create a short, engaging product demo video for {product_text}. "
            f"Show the product in action, highlight its features and benefits. "
            f"Use realistic settings and natural lighting. "
            f"Include a person using or interacting with the product. "
            f"Keep it professional and conversational. "
            f"Duration: 14 seconds.{extra_wishes_text}"
        )
        logger.warning(f"✅ Using fallback prompt ({len(fallback_prompt)} chars): {fallback_prompt[:80]}...")
        return fallback_prompt


async def main():
    global shutdown_flag
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    
    logger.info("🚀 WORKER: started main loop")
    
    # Инициализируем database pool
    try:
        await init_db_pool()
        logger.info("✅ Database pool initialized")
    except Exception as e:
        logger.critical(f"❌ Failed to initialize database pool: {e}")
        raise
    
    # Проверяем наличие критичных переменных
    try:
        # Создаем Bot с увеличенным timeout для отправки больших видео
        # aiogram использует свою собственную сессию, указываем timeout через default
        from aiogram.client.default import DefaultBotProperties
        from aiogram.client.session.aiohttp import AiohttpSession
        import aiohttp
        
        timeout = aiohttp.ClientTimeout(total=600)  # 10 минут для отправки видео
        session = AiohttpSession(timeout=timeout)
        bot = Bot(BOT_TOKEN, session=session)
        logger.info("✅ Bot initialized successfully with 600s timeout")
    except Exception as e:
        logger.critical(f"❌ Failed to initialize bot: {e}")
        await close_db_pool()
        raise
    
    consecutive_errors = 0
    max_consecutive_errors = 5

    try:
        while not shutdown_flag:
            try:
                job = await fetch_next_queued_job()
                
                if not job:
                    logger.debug(f"⏳ No job available, sleeping 2s...")
                    await asyncio.sleep(2)
                    continue

                # Сбрасываем счетчик ошибок при успешном получении задачи
                consecutive_errors = 0
                credit_refunded = False  # Флаг для предотвращения двойного возврата кредитов
                
                job_id = job["id"]
                logger.info(f"💼 Processing job {job_id}")
                
                # Получаем tg_user_id напрямую из job
                tg_user_id = int(job["tg_user_id"])
                kind = job.get("kind") or "reels"

                attempts = int(job.get("attempts") or 0) + 1
                await update_job(job_id, {"status": "processing", "started_at": "NOW()", "attempts": attempts})
                logger.info(f"🔄 Job {job_id} attempt {attempts}")

                input_path = job.get("product_image_url")
                if not input_path:
                    raise RuntimeError("Missing product_image_url")

                image_url = await get_public_input_url(input_path)
                logger.info(f"🖼️ IMAGE_URL: {image_url}")

                # ✅ ВОТ ТУТ теперь выбирается нужный шаблон
                script = build_script_for_job(job)
                logger.info(f"📝 Generated script (first 200 chars): {script[:200]}...")

                try:
                    task_id, api_key = create_task_sora_i2v(prompt=script, image_url=image_url)
                except Exception as e:
                    logger.error(f"❌ Failed to create KIE task: {repr(e)}", exc_info=True)
                    raise
                
                if not task_id:
                    raise RuntimeError("KIE: could not extract task_id")
                
                logger.info(f"✅ KIE task created: {task_id}")
                await update_job(job_id, {"kie_task_id": task_id})

                # Отправляем уведомление только при первой попытке
                if attempts == 1:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    
                    # Кнопки для параллельного заказа ещё видео
                    startup_markup = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Сделать ещё с этим товаром", callback_data="make_another_same_product")],
                        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
                    ])
                    
                    await bot.send_message(
                        tg_user_id,
                        "🎬 <b>Генерация запущена!</b>\n\n"
                        "⏱ Обработка занимает от <b>1 до 30 минут</b> в зависимости от загруженности Sora 2.\n\n"
                        "Я отправлю видео сюда, как только оно будет готово 🎥\n\n"
                        "<i>💡 Можешь заказать ещё видео с этим товаром пока обрабатывается это!</i>",
                        parse_mode="HTML",
                        reply_markup=startup_markup,
                    )

                # REMOVED: Дублирующее уведомление "Фото прошло проверку" - уже есть "Генерация запущена"
                accepted_notified = False
                try:
                    initial_info = await fetch_record_info_once(task_id, api_key)
                    data0 = initial_info.get("data") if isinstance(initial_info, dict) else {}
                    status0 = (data0.get("state") or data0.get("status") or "").lower()
                    fail_msg0 = data0.get("failMsg") if isinstance(data0, dict) else ""
                    fail_code0 = data0.get("failCode") if isinstance(data0, dict) else ""

                    if status0 in {"waiting", "processing", "running", "queued", "pending", "doing"}:
                        # Already notified with "Генерация запущена" and "Фото прошло проверку" messages above
                        accepted_notified = True
                    elif status0 in {"failed", "fail", "error", "canceled", "cancelled"}:
                        logger.warning(f"❌ Initial KIE status fail: code={fail_code0}, msg={fail_msg0}")
                        error_type, error_msg = classify_kie_error(initial_info)
                        await refund_credit(tg_user_id)
                        credit_refunded = True
                        await update_job(job_id, {"status": "failed", "error": error_msg, "finished_at": "NOW()"})
                        
                        # Показываем реальное сообщение об ошибке от Sora если есть
                        if error_type == KieErrorType.USER_VIOLATION:
                            user_msg = (
                                "⚠️ <b>Контент не прошёл модерацию</b>\n\n"
                            )
                            # Добавляем реальное сообщение от Sora если есть
                            if fail_msg0:
                                user_msg += f"🔴 <b>Причина:</b> {fail_msg0}\n\n"
                            user_msg += (
                                "💡 <b>Что делать:</b>\n"
                                "• Загрузите другое фото (без людей и провокационного контента)\n"
                                "• Измените описание товара на более нейтральное\n"
                                "• Попробуйте более простой и спокойный стиль\n\n"
                                "💰 1 кредит вернул на баланс ✅"
                            )
                        else:
                            user_msg = (
                                "⚠️ <b>Фото не прошло проверку Sora 2</b>\n\n"
                                "💡 Требования к фото:\n"
                                "• Без людей и лиц\n"
                                "• Один товар, чётко и без водяных знаков\n"
                                "• JPG/PNG до 5 МБ, вертикально или квадрат\n\n"
                                "💰 1 кредит вернул на баланс ✅"
                            )
                        await bot.send_message(
                            tg_user_id,
                            user_msg,
                            parse_mode="HTML",
                            reply_markup=kb_result(kind),
                        )
                        await asyncio.sleep(1)
                        continue
                except Exception as e:
                    logger.warning(f"⚠️ Initial recordInfo check failed: {e}")
                
                logger.info(f"⏳ Polling KIE for task {task_id}...")
                # Увеличим таймаут до 6 минут (360 сек) для большей надежности
                info = await asyncio.to_thread(poll_record_info, task_id, api_key, 1800, 15)

                logger.info("\n==== KIE recordInfo raw ====")
                logger.info(json.dumps(info, ensure_ascii=False, indent=2))
                logger.info("==== /KIE recordInfo raw ====\n")

                fail_msg = extract_fail_message(info)
                if fail_msg:
                    logger.warning(f"❌ KIE generation failed: {fail_msg}")
                    
                    # Классифицируем ошибку
                    error_type, error_msg = classify_kie_error(info)
                    logger.info(f"🔍 Error classified as: {error_type.value}")
                    
                    # Обновляем health rotator'а
                    rotator = get_rotator()
                    if error_type == KieErrorType.RATE_LIMIT:
                        rotator.report_rate_limit(api_key)
                    elif error_type == KieErrorType.BILLING:
                        rotator.report_billing_error(api_key)
                    else:
                        rotator.report_success(api_key)  # не проблема с ключом
                    
                    # Проверяем нужен ли retry
                    if should_retry(error_type, attempts):
                        retry_delay = get_retry_delay(error_type, attempts)
                        logger.info(f"🔄 Will retry job {job_id} after {retry_delay}s (attempt {attempts}/{MAX_RETRY_ATTEMPTS})")
                        
                        # Уведомляем пользователя о retry
                        if error_type == KieErrorType.TEMPORARY:
                            await bot.send_message(
                                tg_user_id,
                                f"⏳ <b>Sora 2 перегружена</b>\n\n"
                                f"Автоматически пробуем снова (попытка {attempts} из {MAX_RETRY_ATTEMPTS})...\n"
                                f"Это может занять несколько минут.",
                                parse_mode="HTML",
                            )
                        elif error_type == KieErrorType.RATE_LIMIT:
                            await bot.send_message(
                                tg_user_id,
                                f"⏳ <b>Превышен лимит запросов</b>\n\n"
                                f"Автоматически пробуем с другим ключом (попытка {attempts} из {MAX_RETRY_ATTEMPTS})...",
                                parse_mode="HTML",
                            )
                        
                        # Возвращаем job обратно в очередь для retry
                        await update_job(job_id, {"status": "queued", "attempts": attempts})
                        
                        # Ждём перед retry
                        logger.info(f"⏳ Sleeping {retry_delay}s before retry...")
                        await asyncio.sleep(retry_delay)
                        continue
                    
                    # Финальный fail - возвращаем кредит и уведомляем
                    await refund_credit(tg_user_id)
                    credit_refunded = True
                    await update_job(job_id, {"status": "failed", "error": error_msg, "finished_at": "NOW()"})
                    
                    await bot.send_message(
                        tg_user_id,
                        get_user_error_message(error_type),
                        reply_markup=kb_result(kind),
                        parse_mode="HTML",
                    )
                    await asyncio.sleep(1)
                    continue

                video_url = find_video_url(info)
                if not video_url:
                    logger.warning("❌ Video URL not found in KIE response")
                    await refund_credit(tg_user_id)
                    credit_refunded = True
                    await update_job(job_id, {"status": "failed", "error": "no_video_url", "finished_at": "NOW()"})
                    await bot.send_message(
                        tg_user_id,
                        "❌ Я дождался ответа KIE, но не нашёл ссылку на видео. Кредит вернул ✅",
                        reply_markup=kb_result(kind),
                    )
                    await asyncio.sleep(1)
                    continue
                
                logger.info(f"✅ Video URL found: {video_url}")
                
                # Отмечаем успешное использование API ключа
                rotator = get_rotator()
                rotator.report_success(api_key)
                
                # Скачиваем видео с retry для timeout ошибок
                logger.info(f"📥 Downloading video from {video_url}...")
                download_attempts = 0
                max_download_attempts = 5
                data = None
                
                while download_attempts < max_download_attempts:
                    download_attempts += 1
                    try:
                        data = await download_bytes(video_url)
                        logger.info(f"✅ Downloaded {len(data)} bytes")
                        break
                    except httpx.TimeoutException as e:
                        logger.warning(f"⏱️ Download timeout (attempt {download_attempts}/{max_download_attempts}): {e}")
                        if download_attempts >= max_download_attempts:
                            logger.error(f"❌ Video download failed after {max_download_attempts} attempts")
                            raise
                        wait_time = 10 * download_attempts
                        logger.info(f"⏳ Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    except Exception as e:
                        logger.error(f"❌ Download error: {e}")
                        raise
                
                if not data:
                    raise RuntimeError("Failed to download video after retries")

                max_bytes = 45 * 1024 * 1024
                if len(data) > max_bytes:
                    logger.info(f"⚠️ Video too large ({len(data)} bytes), sending URL instead")
                    await update_job(job_id, {"status": "completed", "finished_at": "NOW()", "video_url": video_url})
                    await bot.send_message(
                        tg_user_id,
                        f"✅ Видео готово! Ссылка:\n{video_url}",
                        reply_markup=kb_result(kind),
                    )
                else:
                    logger.info(f"📤 Preparing to send video to user {tg_user_id}")
                    # Готовим кнопки с retry
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    retry_markup = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Сделать ещё с этим товаром", callback_data=f"retry:{job_id}")],
                        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
                    ])
                    
                    # Клавиатура только для видео-сообщения (без кнопки "Сделать ещё")
                    video_markup = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
                    ])
                    
                    video_file_id = ""
                    
                    # СТРАТЕГИЯ: Сначала загружаем в служебный канал (с большим timeout),
                    # затем отправляем пользователю по file_id (мгновенно)
                    if SERVICE_CHANNEL_ID:
                        try:
                            logger.info(f"📤 Pre-uploading video to service channel {SERVICE_CHANNEL_ID}...")
                            service_msg = await bot.send_video(
                                SERVICE_CHANNEL_ID,
                                video=BufferedInputFile(data, filename="reels.mp4"),
                                caption=f"Job: {job_id}",
                                request_timeout=600,  # Большой timeout для первой загрузки
                            )
                            video_file_id = service_msg.video.file_id if service_msg.video else ""
                            logger.info(f"✅ Pre-uploaded to service channel, file_id: {video_file_id[:30]}...")
                            
                            # Отправляем пользователю по file_id (мгновенно!)
                            logger.info(f"📤 Sending video to user {tg_user_id} via file_id...")
                            await bot.send_video(
                                tg_user_id,
                                video=video_file_id,
                                caption="✅ <b>Видео готово!</b>",
                                parse_mode="HTML",
                                reply_markup=video_markup,
                                request_timeout=30,  # Быстро
                            )
                            logger.info(f"✅ Video sent to user via file_id")
                            
                            # Отправляем финальное сообщение об итоге
                            try:
                                await bot.send_message(
                                    tg_user_id,
                                    "🎉 <b>Видео успешно готово и отправлено!</b>\n\n"
                                    "💡 Результат в видео выше ☝️\n\n"
                                    "🎬 Можешь заказать ещё видео этого товара или вернуться в меню",
                                    parse_mode="HTML",
                                    reply_markup=retry_markup,
                                )
                                logger.info(f"✅ Final result message sent")
                            except Exception as msg_error:
                                logger.error(f"⚠️ Failed to send final message: {msg_error}")
                            
                        except Exception as upload_error:
                            logger.error(f"❌ Failed to pre-upload to service channel: {upload_error}")
                            # Fallback: отправляем напрямую
                            logger.info(f"📤 Fallback: sending directly to user...")
                            video_msg = await bot.send_video(
                                tg_user_id,
                                video=BufferedInputFile(data, filename="reels.mp4"),
                                caption="✅ <b>Видео готово!</b>",
                                parse_mode="HTML",
                                reply_markup=video_markup,
                                request_timeout=600,
                            )
                            video_file_id = video_msg.video.file_id if video_msg.video else ""
                    else:
                        # Если SERVICE_CHANNEL_ID не настроен - отправляем напрямую
                        logger.info(f"📤 Sending video directly to user {tg_user_id}...")
                        video_msg = await bot.send_video(
                            tg_user_id,
                            video=BufferedInputFile(data, filename="reels.mp4"),
                            caption="✅ <b>Видео готово!</b>",
                            parse_mode="HTML",
                            reply_markup=video_markup,
                            request_timeout=600,
                        )
                        video_file_id = video_msg.video.file_id if video_msg.video else ""
                    
                    # Сохраняем file_id для быстрых повторных отправок
                    await update_job(job_id, {
                        "status": "completed",
                        "finished_at": "NOW()",
                        "video_url": video_url,
                        "video_file_id": video_file_id  # сохраняем для повторной отправки
                    })
                    logger.info(f"✅ Job {job_id} completed successfully")
                    if video_file_id:
                        logger.info(f"💾 Saved file_id for fast resend: {video_file_id[:30]}...")

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ WORKER_ERROR (attempt {consecutive_errors}/{max_consecutive_errors}): {repr(e)}", exc_info=True)
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"💥 Too many consecutive errors ({max_consecutive_errors}), shutting down...")
                    break
                
                try:
                    if 'tg_user_id' in locals() and not credit_refunded:
                        await refund_credit(tg_user_id)
                        credit_refunded = True
                except Exception:
                    pass
                
                if 'job_id' in locals():
                    try:
                        await update_job(job_id, {"status": "failed", "error": str(e), "finished_at": "NOW()"})
                    except Exception:
                        pass
                
                try:
                    if 'tg_user_id' in locals() and 'job' in locals():
                        error_type = KieErrorType.UNKNOWN
                        error_msg = str(e)
                        
                        logger.info(f"🔍 Processing error for user {tg_user_id}: {type(e).__name__} - {error_msg[:100]}")
                        
                        # Проверяем OpenAI ошибки
                        if hasattr(e, "openai_info"):
                            try:
                                error_type, error_msg = classify_kie_error(e.openai_info)
                                logger.info(f"✅ OpenAI error classified as: {error_type.value} - {error_msg[:100]}")
                            except Exception as classify_error:
                                logger.error(f"⚠️ Failed to classify OpenAI error: {classify_error}")
                        # Проверяем KIE ошибки
                        elif hasattr(e, "kie_info"):
                            try:
                                error_type, error_msg = classify_kie_error(e.kie_info)
                                logger.info(f"✅ KIE error classified as: {error_type.value} - {error_msg[:100]}")
                            except Exception as classify_error:
                                logger.error(f"⚠️ Failed to classify KIE error: {classify_error}")
                        else:
                            logger.warning(f"⚠️ Exception has no error info (openai_info/kie_info), will use generic message")
                        
                        user_msg = get_user_error_message(error_type)
                        if error_type == KieErrorType.UNKNOWN:
                            user_msg = f"❌ Произошла ошибка генерации. 1 кредит вернулся на баланс ✅\n{error_msg}"

                        logger.info(f"📤 Sending message to user {tg_user_id}: {user_msg[:50]}...")
                        await bot.send_message(
                            tg_user_id,
                            user_msg,
                            reply_markup=kb_result(job.get("kind") or "reels"),
                        )
                        logger.info(f"✅ Message sent to user {tg_user_id}")
                except Exception as notify_error:
                    logger.error(f"❌ Failed to notify user {tg_user_id}: {notify_error}", exc_info=True)

            await asyncio.sleep(1)
    finally:
        # Закрываем database pool и bot session при выходе
        if 'session' in locals() and session:
            await session.close()
            logger.info("✅ Bot session closed")
        await close_db_pool()
        logger.info("✅ Database pool closed")
    
    logger.info("✅ Worker main loop ended gracefully")


if __name__ == "__main__":
    retry_count = 0
    max_retries = 3
    retry_delay = 10
    
    while retry_count < max_retries:
        try:
            logger.info(f"🚀 Starting worker (attempt {retry_count + 1}/{max_retries})")
            asyncio.run(main())
            logger.info("✅ Worker exited normally")
            break
        except KeyboardInterrupt:
            logger.info("⚠️ Worker interrupted by user")
            break
        except Exception as e:
            retry_count += 1
            logger.critical(
                f"💥 WORKER_FATAL_ERROR (attempt {retry_count}/{max_retries}):\n{traceback.format_exc()}",
                exc_info=True
            )
            
            if retry_count < max_retries:
                logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.critical("❌ Maximum retry attempts reached. Worker shutting down.")
                # Держим процесс живым чтобы Render не перезапускал слишком часто
                logger.info("⏸️ Keeping process alive for 60 seconds before exit...")
                time.sleep(60)
