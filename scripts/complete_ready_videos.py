#!/usr/bin/env python3
"""
Скрипт для завершения задач, которые уже готовы на KIE.AI но зависли в статусе processing
"""
import asyncio
import os
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile

from app.config import BOT_TOKEN
from app.db_adapter import get_pool, close_db_pool
from worker.video_processor import find_video_url


async def download_video(url: str) -> bytes:
    """Скачать видео по URL"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content


async def check_and_complete_job(job_id: str, tg_user_id: int, kie_task_id: str, kind: str):
    """Проверить задачу на KIE и завершить если готова"""
    kie_api_key = os.getenv("KIE_API_KEY")
    
    # Проверяем статус на KIE
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://api.kie.ai/api/v1/jobs/recordInfo?taskId={kie_task_id}",
            headers={"Authorization": f"Bearer {kie_api_key}"}
        )
        info = response.json()
    
    data = info.get("data", {})
    state = data.get("state", "").lower()
    
    print(f"Job {job_id}: KIE state = {state}")
    
    if state != "success":
        print(f"  ⏭️  Skipping (not ready)")
        return False
    
    # Получаем URL видео
    video_url = find_video_url(info)
    if not video_url:
        print(f"  ❌ No video URL found")
        return False
    
    print(f"  🎬 Video URL: {video_url}")
    
    # Скачиваем видео
    try:
        video_bytes = await download_video(video_url)
        print(f"  📥 Downloaded {len(video_bytes)} bytes")
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        return False
    
    # Отправляем в Telegram
    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.send_video(
            tg_user_id,
            BufferedInputFile(video_bytes, filename="video.mp4"),
            caption="✅ Ваше видео готово!"
        )
        print(f"  ✅ Video sent to user {tg_user_id}")
    except Exception as e:
        print(f"  ❌ Send failed: {e}")
        await bot.session.close()
        return False
    finally:
        await bot.session.close()
    
    # Обновляем статус в базе
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE jobs 
            SET status = 'done', 
                output_url = $1, 
                finished_at = NOW()
            WHERE id = $2
            """,
            video_url, job_id
        )
    print(f"  ✅ Database updated")
    
    return True


async def main():
    """Основная функция"""
    print("🔍 Checking processing jobs...\n")
    
    # Получаем зависшие задачи
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, tg_user_id, kie_task_id, kind 
            FROM jobs 
            WHERE status = 'processing' 
            ORDER BY created_at DESC
            """
        )
    
    if not rows:
        print("✅ No processing jobs found")
        return
    
    print(f"Found {len(rows)} processing jobs\n")
    
    completed = 0
    for row in rows:
        job_id = str(row['id'])
        tg_user_id = row['tg_user_id']
        kie_task_id = row['kie_task_id']
        kind = row['kind']
        
        try:
            if await check_and_complete_job(job_id, tg_user_id, kie_task_id, kind):
                completed += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        print()
    
    print(f"\n✅ Completed {completed}/{len(rows)} jobs")
    
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
