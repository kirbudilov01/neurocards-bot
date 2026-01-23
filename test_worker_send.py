#!/usr/bin/env python3
"""
Тест отправки сообщения через Worker Bot с прокси
Запустить в worker контейнере: python test_worker_send.py
"""
import asyncio
import sys
import os

# Добавляем путь к app
sys.path.insert(0, '/app')

from aiogram import Bot
from aiogram.types import BufferedInputFile
from app.proxy_rotator import init_proxy_rotator, get_proxy_rotator
from app.config import PROXY_FILE
from worker.config import BOT_TOKEN


async def test_send():
    print("🧪 Testing Worker Bot send with proxy...")
    
    # 1. Инициализируем прокси
    try:
        init_proxy_rotator(PROXY_FILE)
        print(f"✅ ProxyRotator initialized from {PROXY_FILE}")
    except Exception as e:
        print(f"❌ ProxyRotator init failed: {e}")
        return False
    
    # 2. Получаем прокси
    proxy_rotator = get_proxy_rotator()
    if not proxy_rotator:
        print("❌ ProxyRotator not available")
        return False
    
    proxy_url = proxy_rotator.get_next_proxy()
    if not proxy_url:
        print("❌ No proxy available")
        return False
    
    print(f"🔄 Using proxy: {proxy_url[:40]}...")
    
    # 3. Создаем Bot с прокси (как в video_processor.py)
    bot = Bot(token=BOT_TOKEN, proxy=proxy_url)
    
    # 4. Отправляем тестовое сообщение
    try:
        tg_user_id = 5235703016  # @kirbudilov01
        
        print(f"📤 Sending test message to user {tg_user_id}...")
        
        await asyncio.wait_for(
            bot.send_message(
                tg_user_id,
                "🧪 <b>Тест отправки из Worker</b>\n\n"
                "✅ Прокси работает!\n"
                "✅ Worker Bot может отправлять сообщения!\n\n"
                f"🔄 Proxy: {proxy_url[:30]}...",
                parse_mode="HTML"
            ),
            timeout=30.0
        )
        
        print("✅ Message sent successfully!")
        return True
        
    except asyncio.TimeoutError:
        print("❌ Send timeout after 30s")
        return False
    except Exception as e:
        print(f"❌ Send failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await bot.session.close()


if __name__ == "__main__":
    result = asyncio.run(test_send())
    sys.exit(0 if result else 1)
