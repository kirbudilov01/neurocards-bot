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
from worker.kie_client import create_task_sora_i2v, poll_record_info
from worker.kie_error_classifier import classify_kie_error, should_retry, get_retry_delay, get_user_error_message, KieErrorType
from worker.kie_key_rotator import get_rotator
from worker.openai_prompter import build_prompt_with_gpt
from worker.prompt_templates import TEMPLATES  # ✅ ВАЖНО

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
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
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


def build_script_for_job(job: dict) -> str:
    """
    ✅ ВАЖНО: тут выбираем шаблон по job.template_id
    """
    template_id = (job.get("template_id") or "ugc").strip()
    tpl = TEMPLATES.get(template_id) or TEMPLATES.get("ugc")

    # product_info может быть строкой (JSON) или dict - фикс для PostgreSQL
    # product_info может быть строкой (JSON) или dict - фикс для PostgreSQL
    product_info = job.get("product_info") or {}
    if isinstance(product_info, str):
        import json
        try:
            product_info = json.loads(product_info)
        except:
            product_info = {}
    
    product_text = (product_info.get("text") or "").strip()
    extra_wishes = job.get("extra_wishes")

    # 🧑‍💻 Сам себе продюсер — GPT НЕ нужен
    if tpl.get("type") == "direct":
        user_prompt = (product_info.get("user_prompt") or "").strip()
        if not user_prompt:
            raise RuntimeError("self_template_missing_user_prompt")
        return user_prompt

    # GPT → сценарий/промпт
    return build_prompt_with_gpt(
        system=tpl["system"],
        instructions=tpl["instructions"],
        product_text=product_text,
        extra_wishes=extra_wishes,
    )


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
        bot = Bot(BOT_TOKEN)
        logger.info("✅ Bot initialized successfully")
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
                    await asyncio.sleep(2)
                    continue

                # Сбрасываем счетчик ошибок при успешном получении задачи
                consecutive_errors = 0
                
                job_id = job["id"]
                logger.info(f"💼 Processing job {job_id}")
                
                # Получаем tg_user_id напрямую из job
                tg_user_id = int(job["tg_user_id"])
                kind = job.get("kind") or "reels"

                attempts = int(job.get("attempts") or 0) + 1
                await update_job(job_id, {"status": "processing", "started_at": "NOW()", "attempts": attempts})
                logger.info(f"🔄 Job {job_id} attempt {attempts}")

                input_path = job.get("input_photo_path")
                if not input_path:
                    raise RuntimeError("Missing input_photo_path")

                image_url = await get_public_input_url(input_path)
                logger.info(f"🖼️ IMAGE_URL: {image_url}")

                # ✅ ВОТ ТУТ теперь выбирается нужный шаблон
                script = build_script_for_job(job)
                logger.info(f"📝 Generated script (first 200 chars): {script[:200]}...")

                task_id, api_key = create_task_sora_i2v(prompt=script, image_url=image_url)
                if not task_id:
                    raise RuntimeError("KIE: could not extract task_id")
                
                logger.info(f"✅ KIE task created: {task_id}")
                await update_job(job_id, {"kie_task_id": task_id})

                await bot.send_message(
                    tg_user_id,
                    "🎬 Генерация запущена.\n\n"
                    "⏱ Обычно это занимает от <b>1 до 30 минут</b> в зависимости от загруженности нейросети Sora 2.\n\n"
                    "Ожидайте, я пришлю результат сюда.",
                    parse_mode="HTML",
                )
                
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
                        
                        # Уведомляем пользователя о временной ошибке (только при первом retry)
                        if error_type == KieErrorType.TEMPORARY and attempts == 2:
                            await bot.send_message(
                                tg_user_id,
                                "⚠️ KIE временно недоступен, повторяю попытку...",
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
                
                logger.info(f"📥 Downloading video from {video_url}...")
                data = await download_bytes(video_url)
                logger.info(f"✅ Downloaded {len(data)} bytes")

                max_bytes = 45 * 1024 * 1024
                if len(data) > max_bytes:
                    logger.info(f"⚠️ Video too large ({len(data)} bytes), sending URL instead")
                    await update_job(job_id, {"status": "done", "finished_at": "NOW()", "output_url": video_url})
                    await bot.send_message(
                        tg_user_id,
                        f"✅ Видео готово! Ссылка:\n{video_url}",
                        reply_markup=kb_result(kind),
                    )
                else:
                    logger.info(f"📤 Sending video to user {tg_user_id}")
                    # Готовим кнопки с retry
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    retry_markup = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Сделать ещё с этим товаром", callback_data=f"retry:{job_id}")],
                        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
                    ])
                    
                    await bot.send_video(
                        tg_user_id,
                        video=BufferedInputFile(data, filename="reels.mp4"),
                        caption="✅ <b>Видео готово!</b>",
                        parse_mode="HTML",
                        reply_markup=retry_markup,
                    )
                    await update_job(job_id, {"status": "done", "finished_at": "NOW()", "output_url": video_url})
                    logger.info(f"✅ Job {job_id} completed successfully")

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ WORKER_ERROR (attempt {consecutive_errors}/{max_consecutive_errors}): {repr(e)}", exc_info=True)
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"💥 Too many consecutive errors ({max_consecutive_errors}), shutting down...")
                    break
                
                try:
                    if 'tg_user_id' in locals():
                        await refund_credit(tg_user_id)
                except Exception:
                    pass
                
                if 'job_id' in locals():
                    try:
                        await update_job(job_id, {"status": "failed", "error": str(e), "finished_at": "NOW()"})
                    except Exception:
                        pass
                
                try:
                    if 'tg_user_id' in locals() and 'job' in locals():
                        await bot.send_message(
                            tg_user_id,
                            f"❌ Произошла ошибка генерации. 1 кредит вернулся на баланс ✅\n{e}",
                            reply_markup=kb_result(job.get("kind") or "reels"),
                        )
                except Exception as notify_error:
                    logger.error(f"❌ Failed to notify user: {notify_error}")

            await asyncio.sleep(1)
    finally:
        # Закрываем database pool при выходе
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
