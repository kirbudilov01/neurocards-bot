"""
Telegram bot в режиме polling (без webhook).
Используется для тестирования без домена и SSL сертификата.
"""
import asyncio
import logging
import sys
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

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


async def start_health_server(port: int):
    """Запускает HTTP сервер для healthcheck и отдачи storage файлов."""
    try:
        async def handle_healthz(request):
            return web.Response(text="ok")

        async def handle_storage(request: web.Request):
            # Serve files from STORAGE_BASE_PATH under /storage/{bucket}/{filename}
            bucket = request.match_info.get("bucket", "")
            filename = request.match_info.get("filename", "")
            base_path = os.getenv("STORAGE_BASE_PATH", "/app/storage")
            # Allow only inputs/outputs buckets
            if bucket not in {"inputs", "outputs"}:
                return web.Response(status=404, text="Not found")
            import mimetypes
            from pathlib import Path
            file_path = Path(base_path) / bucket / filename
            if not file_path.exists() or not file_path.is_file():
                return web.Response(status=404, text="Not found")
            ctype, _ = mimetypes.guess_type(str(file_path))
            ctype = ctype or "application/octet-stream"
            try:
                return web.FileResponse(path=str(file_path), headers={"Content-Type": ctype})
            except Exception as e:
                logger.error(f"❌ Failed to serve file {file_path}: {e}")
                return web.Response(status=500, text="Internal server error")

        app = web.Application()
        app.router.add_get("/", handle_healthz)
        app.router.add_get("/healthz", handle_healthz)
        app.router.add_get("/storage/{bucket}/{filename}", handle_storage)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site.start()
        logger.info(f"🩺 Health server started on port {port}")
        
        # Keep the server running indefinitely
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"❌ Failed to start health server on port {port}: {e}", exc_info=True)


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

    # Запускаем легковесный HTTP health сервер, чтобы healthcheck в Docker работал
    port = int(os.getenv("PORT", "8080"))
    asyncio.create_task(start_health_server(port))
    
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
