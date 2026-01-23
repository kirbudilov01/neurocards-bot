#!/usr/bin/env python3
"""
Простой тестовый скрипт для ручной отправки видео в Telegram
Используется для диагностики проблем с отправкой
"""
import asyncio
import os
import sys
from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import ClientTimeout

# Данные
BOT_TOKEN = os.getenv("BOT_TOKEN")
TG_USER_ID = int(os.getenv("TG_USER_ID", "5235703016"))  # ID пользователя по умолчанию
VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "/app/storage/outputs/31d55a86-39f8-4ef8-9389-1b24b845c814.mp4"
PROXY_URL = "socks5://EJjajW:7HG42r@23.236.149.196:9530"  # Первый прокси из proxies.txt

print(f"📤 Отправляем видео: {VIDEO_PATH}")
print(f"👤 Пользователь: {TG_USER_ID}")
print(f"🤖 BOT_TOKEN: {BOT_TOKEN[:20]}...")
print(f"🌐 Прокси: НЕ используется (отправка напрямую)")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не задан!")
    sys.exit(1)

if not os.path.exists(VIDEO_PATH):
    print(f"❌ Видео не найдено: {VIDEO_PATH}")
    sys.exit(1)

async def send_video():
    """Отправить видео в Telegram БЕЗ прокси"""
    try:
        # Таймауты для отправки
        timeout = ClientTimeout(
            total=180.0,
            connect=30.0,
            sock_connect=30.0,
            sock_read=180.0
        )
        
        # БЕЗ прокси (proxy=None)
        session = AiohttpSession(proxy=None, timeout=timeout)
        
        # Создаем бот с сессией
        bot = Bot(token=BOT_TOKEN, session=session)
        
        # Отправляем видео из файла
        file_size = os.path.getsize(VIDEO_PATH)
        print(f"📁 Размер файла: {file_size / 1024 / 1024:.2f} MB")
        
        await bot.send_video(
            TG_USER_ID,
            FSInputFile(VIDEO_PATH),
            caption="✅ Тестовое видео (отправка вручную)"
        )
        
        print("✅ Видео отправлено успешно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при отправке: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await bot.session.close()

if __name__ == "__main__":
    success = asyncio.run(send_video())
    sys.exit(0 if success else 1)
