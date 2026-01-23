"""
Основная логика обработки видео
Выделена в отдельный модуль для переиспользования
"""
import logging
import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from app.db_adapter import update_job, refund_credit, get_user_by_tg_id, init_db_pool, close_db_pool
from app.services.storage_factory import get_storage
from worker.kie_client import create_task_sora_i2v, poll_record_info
from worker.kie_error_classifier import classify_kie_error, should_retry, get_user_error_message
from worker.kie_key_rotator import get_rotator
from worker.openai_prompter import build_prompt_with_gpt
from worker.prompt_templates import TEMPLATES
from worker.config import BOT_TOKEN, MAX_RETRY_ATTEMPTS

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
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


def build_prompt(product_info: dict, template_id: str, extra_wishes: str | None) -> str:
    """Построить промпт для генерации видео"""
    template = TEMPLATES.get(template_id, TEMPLATES.get("ugc"))
    
    # Парсим product_info если это строка
    if isinstance(product_info, str):
        try:
            product_info = json.loads(product_info)
        except:
            product_info = {"text": product_info}
    
    product_text = product_info.get("text", str(product_info))
    
    # Генерируем промпт через GPT
    try:
        prompt = build_prompt_with_gpt(
            system=template["system"],
            instructions=template["instructions"],
            product_text=product_text,
            extra_wishes=extra_wishes
        )
        logger.info(f"✅ GPT generated prompt: {prompt[:100]}...")
        return prompt
    except Exception as e:
        logger.error(f"❌ GPT prompt generation failed: {e}")
        # Fallback к базовому промпту
        return product_text


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
    
    # Инициализируем БД
    await init_db_pool()
    
    try:
        # 1. Обновляем статус в БД
        await update_job(job_id, {"status": "processing", "started_at": datetime.now(timezone.utc).isoformat()})
        
        # 2. Получаем публичный URL фото
        image_url = await get_public_input_url(input_photo_path)
        logger.info(f"📸 Image URL: {image_url}")
        
        # 3. Генерируем промпт
        prompt = build_prompt(product_info, template_id, extra_wishes)
        
        # 4. Создаем задачу в KIE.AI с ротацией ключей
        attempt = 0
        last_error = None
        
        while attempt < MAX_RETRY_ATTEMPTS:
            try:
                kie_task_id, api_key_used = create_task_sora_i2v(prompt, image_url)
                logger.info(f"✅ KIE task created: {kie_task_id}")
                
                # Сохраняем task_id в БД
                await update_job(job_id, {"kie_task_id": kie_task_id})
                
                # 5. Ждем результата
                info = poll_record_info(kie_task_id, api_key_used, timeout_sec=300, interval_sec=10)
                video_url = find_video_url(info)
                
                if not video_url:
                    raise RuntimeError("Video URL not found in KIE response")
                
                logger.info(f"🎬 Video URL: {video_url}")
                
                # 6. Скачиваем и отправляем в Telegram
                video_bytes = await download_bytes(video_url)
                
                bot = Bot(token=BOT_TOKEN)
                await bot.send_video(
                    tg_user_id,
                    BufferedInputFile(video_bytes, filename="video.mp4"),
                    caption="✅ Ваше видео готово!",
                    reply_markup=kb_result(job_data.get("kind", "reels"))
                )
                await bot.session.close()
                
                # 7. Обновляем статус
                await update_job(job_id, {
                    "status": "done",
                    "output_url": video_url,
                    "finished_at": datetime.now(timezone.utc).isoformat()
                })
                
                return {
                    "success": True,
                    "output_url": video_url,
                    "error": None
                }
                
            except Exception as e:
                last_error = e
                error_type = classify_kie_error(str(e))
                
                if should_retry(error_type) and attempt < MAX_RETRY_ATTEMPTS - 1:
                    attempt += 1
                    logger.warning(f"⚠️ Attempt {attempt} failed, retrying...")
                    # Ротируем ключ
                    get_rotator().mark_failed(api_key_used if 'api_key_used' in locals() else None)
                    await asyncio.sleep(5)
                    continue
                else:
                    # Permanent error или исчерпаны попытки
                    logger.error(f"❌ Job {job_id} failed permanently: {e}")
                    
                    # Возвращаем кредит
                    await refund_credit(tg_user_id)
                    
                    # Уведомляем пользователя
                    user_message = get_user_error_message(error_type)
                    bot = Bot(token=BOT_TOKEN)
                    await bot.send_message(
                        tg_user_id,
                        f"❌ {user_message}",
                        parse_mode="HTML"
                    )
                    await bot.session.close()
                    
                    # Обновляем статус
                    await update_job(job_id, {
                        "status": "failed",
                        "error": str(e),
                        "attempts": attempt + 1,
                        "finished_at": datetime.now(timezone.utc).isoformat()
                    })
                    
                    return {
                        "success": False,
                        "output_url": None,
                        "error": str(e)
                    }
        
        raise last_error if last_error else RuntimeError("Unknown error")
        
    finally:
        await close_db_pool()
