import os
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from app.config import BOT_TOKEN
from app.handlers import start, menu_and_flow, fallback
from app.db_adapter import init_db_pool, close_db_pool


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
