<<<<<<< HEAD
"""
Telegram bot в режиме polling (без webhook).
Используется для тестирования без домена и SSL сертификата.
"""
=======
import os
>>>>>>> 8f6520fa9541fa7c865a7c36d6faea7967bcf8fc
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
<<<<<<< HEAD
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector
=======
>>>>>>> 8f6520fa9541fa7c865a7c36d6faea7967bcf8fc
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
<<<<<<< HEAD
    handlers=[logging.StreamHandler(sys.stdout)]
=======
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
>>>>>>> 8f6520fa9541fa7c865a7c36d6faea7967bcf8fc
)
logger = logging.getLogger(__name__)

from app.config import BOT_TOKEN
<<<<<<< HEAD
from app.config import load_proxies_from_file, PROXY_FILE, PROXY_COOLDOWN
from app.proxy_rotator import init_proxy_rotator, get_proxy_rotator
=======
>>>>>>> 8f6520fa9541fa7c865a7c36d6faea7967bcf8fc
from app.handlers import start, menu_and_flow, fallback
from app.db_adapter import init_db_pool, close_db_pool


<<<<<<< HEAD
def create_bot_with_proxy() -> Bot:
    """Создать Bot с поддержкой прокси ротации."""
    # Загрузить прокси
    proxies = load_proxies_from_file(PROXY_FILE)
    
    if not proxies:
        logger.warning("⚠️ No proxies found, bot will work without proxy!")
        return Bot(token=BOT_TOKEN)
    
    # Инициализировать ротатор
    init_proxy_rotator(proxies, cooldown_seconds=PROXY_COOLDOWN)
    rotator = get_proxy_rotator()
    
    # Получить первый прокси (уже форматирован как http://...)
    proxy_url = rotator.get_next_proxy()
    if not proxy_url:
        logger.error("❌ All proxies are blocked! Bot will work without proxy")
        return Bot(token=BOT_TOKEN)
    
    logger.info(f"🔄 Bot using proxy: {proxy_url[:30]}...")
    logger.info(f"✅ Proxy initialized successfully")
    
    # Создать бота БЕЗ кастомной сессии, aiogram 3 поддерживает proxy через параметр
    # Но мы используем connector внутри default session
    return Bot(token=BOT_TOKEN, proxy=proxy_url)


async def main():
    """
    Основная функция - запуск бота в polling режиме
    """
    logger.info("🚀 Starting bot in POLLING mode...")
    
    # Инициализация пула БД
    try:
        await init_db_pool()
        logger.info("✅ Database pool initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database pool: {e}", exc_info=True)
        return

    # Создание бота с прокси
    bot = create_bot_with_proxy()
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(menu_and_flow.router)
    dp.include_router(fallback.router)

    try:
        # Удаляем webhook если был установлен
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted")
        
        # Запускаем polling
        logger.info("🔄 Starting polling...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False
        )
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"❌ Error during polling: {e}", exc_info=True)
    finally:
        await bot.session.close()
        await close_db_pool()
        logger.info("👋 Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
=======
async def main():
    """Polling mode - для разработки и тестирования (не требует HTTPS)"""
    try:
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set")
        
        logger.info("Starting bot in POLLING mode...")
        
        # Инициализируем пул БД
        try:
            await init_db_pool()
            logger.info("✅ Database pool initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database pool: {e}", exc_info=True)
            raise
        
        # Бот и диспетчер
        bot = Bot(BOT_TOKEN)
        dp = Dispatcher(storage=MemoryStorage())
        
        # Роутеры
        dp.include_router(start.router)
        dp.include_router(menu_and_flow.router)
        dp.include_router(fallback.router)
        
        # Удаляем webhook если был установлен
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted, starting polling...")
        
        # Запускаем polling
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            await close_db_pool()
            await bot.session.close()
            logger.info("✅ Bot stopped gracefully")
            
    except Exception as e:
        logger.critical(f"💥 Critical error in main: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
>>>>>>> 8f6520fa9541fa7c865a7c36d6faea7967bcf8fc
