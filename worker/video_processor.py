"""
Основная логика обработки видео
Выделена в отдельный модуль для переиспользования
"""
import logging
import asyncio
import json
import re
import os
from datetime import datetime, timezone

import httpx
from aiogram import Bot
from aiogram.types import FSInputFile, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from app.db_adapter import update_job, refund_credit, get_user_by_tg_id, init_db_pool, close_db_pool
from app.services.storage_factory import get_storage
from app.utils import ensure_dict
from worker.kie_client import create_task_sora_i2v, poll_record_info
from worker.kie_error_classifier import classify_kie_error, should_retry, get_user_error_message
from worker.kie_key_rotator import get_rotator
from worker.openai_prompter import build_prompt_with_gpt
from worker.prompt_templates import TEMPLATES
from worker.config import BOT_TOKEN, MAX_RETRY_ATTEMPTS, STORAGE_BASE_PATH

logger = logging.getLogger(__name__)


def kb_result(kind: str = "reels") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Сгенерировать ещё", callback_data=f"again:{kind}")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


async def get_public_input_url(input_path: str) -> str:
    """Получить публичный URL для input файла"""
    if input_path and (input_path.startswith("http://") or input_path.startswith("https://")):
        return input_path
    
    storage = get_storage()
    rel = (input_path or "").strip().lstrip("/")
    while rel.startswith("inputs/"):
        rel = rel[len("inputs/"):]
    
    return await storage.get_public_url("inputs", rel)


def find_video_url(obj) -> str | None:
    """Найти URL видео в ответе KIE.AI"""
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
    """Скачать видео по URL"""
    # Увеличиваем timeout до 300s (5 минут) на случай больших видео
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        logger.info(f"✅ Downloaded video: {len(r.content) / 1024 / 1024:.2f} MB")
        return r.content


def build_prompt(product_info: dict, template_id: str, extra_wishes: str | None) -> str:
    """Построить промпт для генерации видео"""
    template = TEMPLATES.get(template_id, TEMPLATES.get("ugc"))
    # Гарантируем что product_info это dict
    product_info = ensure_dict(product_info)
    
    product_text = product_info.get("text", str(product_info))
    
    logger.info(f"🎯 Building prompt: template={template_id}, product_length={len(product_text)}, has_wishes={bool(extra_wishes)}")
    
    # Генерируем промпт через GPT
    try:
        prompt = build_prompt_with_gpt(
            system=template["system"],
            instructions=template["instructions"],
            product_text=product_text,
            extra_wishes=extra_wishes
        )
        logger.info(f"✅ GPT generated prompt ({len(prompt)} chars): {prompt[:150]}...")
        return prompt
    except Exception as e:
        logger.error(f"❌ GPT prompt generation failed: {e}, using fallback")
        # Если это OpenAI ошибка с деталями (photorealistic people и т.п.) - пробросим дальше
        if hasattr(e, 'openai_info'):
            raise e
        # Иначе используем fallback промпт
        fallback_prompt = f"A commercial video showing: {product_text}"
        logger.info(f"⚡ Using fallback prompt: {fallback_prompt[:150]}...")
        return fallback_prompt


async def process_video_generation(job_data: dict) -> dict:
    """
    Основная функция обработки видео
    
    Args:
        job_data: данные задачи из Redis
        
    Returns:
        dict: результат обработки
    """
    job_id = job_data["job_id"]
    tg_user_id = job_data["tg_user_id"]
    input_photo_path = job_data["input_photo_path"]
    product_info = job_data["product_info"]
    template_id = job_data.get("template_id", "ugc")
    extra_wishes = job_data.get("extra_wishes")
    
    # Инициализируем БД и прокси
    await init_db_pool()
    
    # Инициализируем ProxyRotator для отправки видео
    try:
        from app.proxy_rotator import init_proxy_rotator
        from app.config import PROXY_FILE, load_proxies_from_file, PROXY_COOLDOWN
        proxies = load_proxies_from_file(PROXY_FILE)
        if proxies:
            init_proxy_rotator(proxies, cooldown_seconds=PROXY_COOLDOWN)
            logger.info(f"✅ ProxyRotator initialized in worker with {len(proxies)} proxies")
        else:
            logger.warning("⚠️ No proxies found, will try to send without proxy")
    except Exception as e:
        logger.warning(f"⚠️ ProxyRotator init failed (will try to send without proxy): {e}")
    
    try:
        # 1. Обновляем статус в БД
        await update_job(job_id, {"status": "processing", "started_at": datetime.now(timezone.utc)})
        
        # 2. Получаем публичный URL фото
        image_url = await get_public_input_url(input_photo_path)
        logger.info(f"📸 Image URL: {image_url}")
        
        # 3. Генерируем промпт
        prompt = build_prompt(product_info, template_id, extra_wishes)
        
        # ========== LOOP 1: ГЕНЕРАЦИЯ ВИДЕО (KIE.AI) ==========
        # Retry только если генерация fail, не если видео просто не готово
        attempt = 0
        last_error = None
        video_url = None
        
        while attempt < MAX_RETRY_ATTEMPTS:
            attempt += 1
            try:
                kie_task_id, api_key_used = create_task_sora_i2v(prompt, image_url)
                logger.info(f"✅ KIE task created: {kie_task_id}")
                
                # Сохраняем task_id в БД
                await update_job(job_id, {"kie_task_id": kie_task_id})
                
                # 5. Ждем результата (Sora-2 может генерировать до 10 минут)
                info = poll_record_info(kie_task_id, api_key_used, timeout_sec=600, interval_sec=10)
                
                # Проверяем state (может быть fail)
                data = info.get("data", {}) if isinstance(info, dict) else {}
                state = data.get("state", "").lower()
                
                if state == "fail" or state == "failed":
                    fail_msg = data.get("failMsg", "Unknown error")
                    fail_code = data.get("failCode", "")
                    error_detail = f"KIE.AI error (code {fail_code}): {fail_msg}"
                    logger.error(f"❌ KIE task failed: {error_detail}")
                    # Создаем exception с info для классификации
                    error = RuntimeError(error_detail)
                    error.kie_info = info  # Прикрепляем полный ответ для классификации
                    raise error
                
                video_url = find_video_url(info)
                
                if not video_url:
                    error_detail = f"Could not find video URL in KIE response"
                    logger.error(f"❌ {error_detail}")
                    error = RuntimeError(error_detail)
                    error.kie_info = info
                    raise error
                
                logger.info(f"🎬 Video URL: {video_url}")
                
                # ✅ УСПЕШНО! Видео готово - выходим из KIE loop (НЕ делаем continue!)
                break
                
            except Exception as e:
                last_error = e
                # Классифицируем ошибку
                if hasattr(e, 'kie_info'):
                    error_type, error_msg = classify_kie_error(e.kie_info)
                else:
                    error_type, error_msg = classify_kie_error({"error": str(e)})
                
                logger.info(f"📊 Classified error: {error_type} - {error_msg}")
                
                if should_retry(error_type, attempt, MAX_RETRY_ATTEMPTS):
                    logger.warning(f"⚠️ Attempt {attempt} failed ({error_type}), retrying KIE generation...")
                    # Ротируем ключ для следующей попытки
                    if 'api_key_used' in locals():
                        try:
                            get_rotator().mark_failed(api_key_used)
                        except:
                            pass
                    await asyncio.sleep(5)
                    continue  # Переходим к следующей итерации while loop
                else:
                    # Permanent error или исчерпаны попытки
                    logger.error(f"❌ Job {job_id} failed permanently: {error_type} - {e}")
                    # Возвращаем кредит
                    await refund_credit(tg_user_id)
                    
                    # Отправляем сообщение об ошибке пользователю
                    try:
                        error_msg_to_user = get_user_error_message(error_type)
                        # Create a temporary bot instance to send message
                        from aiogram.client.session.aiohttp import AiohttpSession
                        from aiohttp import ClientTimeout
                        temp_timeout = ClientTimeout(total=30.0, connect=10.0)
                        temp_session = AiohttpSession(proxy=None, timeout=temp_timeout)
                        temp_bot = Bot(token=BOT_TOKEN, session=temp_session)
                        await temp_bot.send_message(
                            tg_user_id, 
                            error_msg_to_user,
                            parse_mode="HTML"
                        )
                        await temp_session.close()
                    except Exception as send_error:
                        logger.error(f"⚠️ Failed to send error message to user: {send_error}")
                    
                    raise RuntimeError(f"Generation failed: {error_type} - {e}")
        
        # После KIE loop мы имеем video_url готовый к отправке!
        if not video_url:
            logger.error(f"❌ Failed to get video URL from KIE after {attempt} attempts")
            await refund_credit(tg_user_id)
            raise RuntimeError("Failed to generate video")
        
        # ========== LOOP 2: ОТПРАВКА ВИДЕО ==========
        # Скачиваем видео один раз
        video_bytes = await download_bytes(video_url)
        logger.info(f"✅ Downloaded video: {len(video_bytes)/1024/1024:.2f} MB")

        # Сохраняем видео в локальное хранилище, чтобы отправлять из файла
        os.makedirs(os.path.join(STORAGE_BASE_PATH, "outputs"), exist_ok=True)
        video_path = os.path.join(STORAGE_BASE_PATH, "outputs", f"{job_id}.mp4")
        try:
            with open(video_path, "wb") as f:
                f.write(video_bytes)
            logger.info(f"💾 Saved video to {video_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save video to storage: {e}")
            await refund_credit(tg_user_id)
            raise
        
        # Отправка видео имеет отдельный retry механизм (не создавать новое видео!)
        send_attempts = 0
        send_error = None
        
        while send_attempts < 3:  # 3 попытки отправить существующее видео
            send_attempts += 1
            try:
                # Создаем Bot с таймаутами для отправки
                from aiogram.client.session.aiohttp import AiohttpSession
                from aiohttp import ClientTimeout
                
                # Таймауты для ОТПРАВКИ в Telegram (короче, чем генерация KIE)
                timeout = ClientTimeout(
                    total=180.0,        # 3 минуты на весь запрос
                    connect=30.0,       # 30 секунд на connect
                    sock_connect=30.0,  # 30 секунд на socket connect
                    sock_read=180.0     # 3 минуты на чтение/upload
                )
                
                # Используем простую отправку БЕЗ прокси (работает!)
                session = AiohttpSession(proxy=None, timeout=timeout)
                bot = Bot(token=BOT_TOKEN, session=session)
                
                logger.info(f"📤 Send attempt {send_attempts}/3: Sending video (timeout: {timeout.total}s)")
                
                # Отправляем видео БЕЗ asyncio.wait_for (timeout уже в session)
                await bot.send_video(
                    tg_user_id,
                    FSInputFile(video_path),
                    caption="✅ Ваше видео готово!",
                    reply_markup=kb_result(job_data.get("kind", "reels"))
                )
                logger.info(f"✅ Video sent successfully to user {tg_user_id}")
                
                # Success! Break из send_attempts loop
                break
                
            except Exception as send_error_exc:
                send_error = send_error_exc
                logger.warning(f"⚠️ Send attempt {send_attempts}/3 failed: {type(send_error).__name__}: {send_error}")
                
                if send_attempts < 3:
                    logger.info(f"⏳ Retrying send in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    # ✅ Исчерпаны попытки отправки - ВОЗВРАЩАЕМ КРЕДИТЫ И УВЕДОМЛЯЕМ!
                    logger.error(f"❌ Failed to send video after {send_attempts} attempts: {send_error}")
                    logger.info(f"💰 Refunding credits to user {tg_user_id} due to send failure")
                    
                    # Возвращаем кредиты
                    try:
                        await refund_credit(tg_user_id)
                    except Exception as refund_error:
                        logger.error(f"⚠️ Failed to refund credits: {refund_error}")
                    
                    # Отправляем сообщение пользователю о ошибке отправки
                    try:
                        from aiogram.client.session.aiohttp import AiohttpSession
                        from aiohttp import ClientTimeout
                        temp_timeout = ClientTimeout(total=30.0, connect=10.0)
                        temp_session = AiohttpSession(proxy=None, timeout=temp_timeout)
                        temp_bot = Bot(token=BOT_TOKEN, session=temp_session)
                        
                        error_msg = (
                            "🌐 <b>Ошибка при отправке видео</b>\n\n"
                            "Видео успешно сгенерировано, но не удалось отправить в Telegram.\n\n"
                            "💰 1 кредит вернули на баланс ✅\n\n"
                            "🔄 Попробуйте еще раз позже."
                        )
                        
                        await temp_bot.send_message(
                            tg_user_id,
                            error_msg,
                            parse_mode="HTML",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                InlineKeyboardButton(text="🔄 Попробовать еще", callback_data="back_to_menu")
                            ]])
                        )
                        await temp_session.close()
                    except Exception as msg_error:
                        logger.error(f"⚠️ Failed to notify user about send error: {msg_error}")
                    
                    # Обновляем status в базе как failed
                    try:
                        await update_job(job_id, {
                            "status": "failed",
                            "error_message": f"Send failed after 3 attempts: {send_error}",
                            "finished_at": datetime.now(timezone.utc)
                        })
                    except Exception as update_error:
                        logger.error(f"⚠️ Failed to update job status: {update_error}")
                    
                    raise RuntimeError(f"Video send failed after {send_attempts} attempts: {send_error}")
            finally:
                try:
                    await session.close()
                except:
                    pass
        
        # 7. Обновляем статус в "done"
        await update_job(job_id, {
            "status": "done",
            "output_url": video_url,
            "finished_at": datetime.now(timezone.utc)
        })

        # Удаляем локальный файл после успешной отправки
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
                logger.info(f"🧹 Deleted local video file {video_path}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to delete local video file {video_path}: {e}")
        
        return {
            "success": True,
            "output_url": video_url,
            "error": None
        }
    
    finally:
        await close_db_pool()
