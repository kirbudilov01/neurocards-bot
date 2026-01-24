"""
Telegram bot в режиме polling (без webhook).
Используется для тестирования без домена и SSL сертификата.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from app.config import BOT_TOKEN
from app.config import load_proxies_from_file, PROXY_FILE, PROXY_COOLDOWN
from app.proxy_rotator import init_proxy_rotator, get_proxy_rotator
from app.handlers import start, menu_and_flow, fallback
from app.db_adapter import init_db_pool, close_db_pool


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
    
    # Создать бота с увеличенным таймаутом для отправки больших файлов
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    
    return Bot(
        token=BOT_TOKEN,
        proxy=proxy_url,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        request_timeout=120  # 120 секунд для больших файлов
    )


async def main():
    """
    Основная функция - запуск бота в polling режиме
    """
    logger.info("🚀 Starting bot in POLLING mode (WITHOUT PROXY)...")
    
    # Инициализация пула БД
    try:
        await init_db_pool()
        logger.info("✅ Database pool initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database pool: {e}", exc_info=True)
        return

    # Создание бота БЕЗ прокси (прокси нужен только для GPT, не для Telegram)
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.client.session.aiohttp import AiohttpSession
    
    # Увеличиваем timeout для загрузки больших файлов (видео)
    session = AiohttpSession(timeout=180)  # 3 минуты вместо 60 секунд
    
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session
    )
    logger.info("✅ Bot initialized WITHOUT proxy (request_timeout=180s)")
    
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
