import os
import asyncio
import logging
import sys
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage  # 🔥 КРИТИЧЕСКИ ВАЖНО

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from app.config import BOT_TOKEN, PUBLIC_BASE_URL, WEBHOOK_SECRET_TOKEN
from app.config import load_proxies_from_file, PROXY_FILE, PROXY_COOLDOWN
from app.proxy_rotator import init_proxy_rotator, get_proxy_rotator
from app.handlers import start, menu_and_flow, fallback
from app.db_adapter import init_db_pool, close_db_pool


WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = f"{PUBLIC_BASE_URL.rstrip('/')}{WEBHOOK_PATH}"


def create_bot_with_proxy() -> Bot:
    """
    Создать Bot с поддержкой прокси ротации.
    
    Returns:
        Bot инстанс с настроенной сессией
    """
    # Загрузить прокси
    proxies = load_proxies_from_file(PROXY_FILE)
    
    if not proxies:
        logger.warning("⚠️ No proxies found, bot will work without proxy!")
        return Bot(token=BOT_TOKEN)
    
    # Инициализировать ротатор
    init_proxy_rotator(proxies, cooldown_seconds=PROXY_COOLDOWN)
    rotator = get_proxy_rotator()
    
    # Получить первый прокси
    proxy = rotator.get_next_proxy()
    if not proxy:
        logger.error("❌ All proxies are blocked! Bot will work without proxy")
        return Bot(token=BOT_TOKEN)
    
    # Форматировать для aiohttp (нужен http:// формат для aiohttp-socks)
    proxy_url = rotator.format_for_aiohttp(proxy)
    logger.info(f"🔄 Bot using proxy: {rotator._mask_proxy(proxy)}")
    
    # Создать connector с прокси
    connector = ProxyConnector.from_url(proxy_url)
    
    # Создать сессию с connector - aiogram сам создаст ClientSession внутри
    session = AiohttpSession(connector=connector)
    
    return Bot(token=BOT_TOKEN, session=session)

async def on_startup(bot: Bot):
    """
    Действия при запуске:
    - Инициализируем пул БД
    - Устанавливаем webhook
    """
    try:
        # Инициализируем пул подключений к БД
        await init_db_pool()
        logger.info("✅ Database pool initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database pool: {e}", exc_info=True)
        raise
    
    try:
        await bot.set_webhook(
            WEBHOOK_URL,
            drop_pending_updates=True,
            secret_token=WEBHOOK_SECRET_TOKEN,
        )
        logger.info(f"✅ Webhook set successfully: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Failed to set webhook: {e}", exc_info=True)
        raise


async def on_shutdown(bot: Bot):
    """
    Действия при выключении:
    - Удаляем webhook
    - Закрываем пул БД
    - Закрываем сессию
    """
    try:
        await bot.delete_webhook()
        logger.info("✅ Webhook deleted")
    except Exception as e:
        logger.error(f"⚠️ Error deleting webhook: {e}")
    
    try:
        await close_db_pool()
        logger.info("✅ Database pool closed")
    except Exception as e:
        logger.error(f"⚠️ Error closing database pool: {e}")
    
    try:
        await bot.session.close()
        logger.info("✅ Bot session closed")
    except Exception as e:
        logger.error(f"⚠️ Error closing session: {e}")


async def handle_healthz(request):
    return web.Response(text="ok")


async def handle_queue_stats(request):
    """Endpoint для мониторинга очереди заданий"""
    try:
        from app.db_adapter import get_pool, DATABASE_TYPE
        
        if DATABASE_TYPE == "postgres":
            pool = await get_pool()
            async with pool.acquire() as conn:
                # Считаем задания по статусам
                queued = await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'queued'")
                processing = await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE status = 'processing'")
                
                # Средний возраст задач в очереди (в минутах)
                avg_wait = await conn.fetchval("""
                    SELECT EXTRACT(EPOCH FROM (NOW() - AVG(created_at))) / 60
                    FROM jobs WHERE status = 'queued'
                """)
                
                # Количество активных воркеров (processing задачи + буфер)
                # Каждый воркер берет задачу на ~5-10 минут
                
                return web.json_response({
                    "status": "ok",
                    "queue": {
                        "queued": queued or 0,
                        "processing": processing or 0,
                        "total": (queued or 0) + (processing or 0)
                    },
                    "avg_wait_minutes": round(avg_wait or 0, 1),
                    "workers_configured": int(os.getenv("WORKER_INSTANCES", "1")),
                    "timestamp": asyncio.get_event_loop().time()
                })
        else:
            # Supabase fallback
            from app.db_adapter import supabase
            
            queued_res = await asyncio.to_thread(
                lambda: supabase.table("jobs").select("id", count="exact").eq("status", "queued").execute()
            )
            processing_res = await asyncio.to_thread(
                lambda: supabase.table("jobs").select("id", count="exact").eq("status", "processing").execute()
            )
            
            return web.json_response({
                "status": "ok",
                "queue": {
                    "queued": queued_res.count or 0,
                    "processing": processing_res.count or 0,
                    "total": (queued_res.count or 0) + (processing_res.count or 0)
                },
                "workers_configured": int(os.getenv("WORKER_INSTANCES", "1")),
                "timestamp": asyncio.get_event_loop().time()
            })
    except Exception as e:
        logger.error(f"❌ Error in queue_stats: {e}", exc_info=True)
        return web.json_response({
            "status": "error",
            "error": str(e)
        }, status=500)


async def main():
    try:
        # Проверка обязательных переменных окружения
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set")
        if not PUBLIC_BASE_URL:
            raise ValueError("PUBLIC_BASE_URL is not set")
        
        logger.info("Starting bot initialization...")
        
        # 🔑 Бот с поддержкой прокси
        bot = create_bot_with_proxy()

        # ✅ FSM будет РАБОТАТЬ
        dp = Dispatcher(storage=MemoryStorage())

        # 📞 Вешаем startup/shutdown обработчики
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        # 📦 Роутеры (порядок важен)
        dp.include_router(start.router)
        dp.include_router(menu_and_flow.router)
        dp.include_router(fallback.router)  # ВСЕГДА ПОСЛЕДНИМ

        # 🌐 Web app
        app = web.Application()

        # Health check endpoints
        app.router.add_get("/", handle_healthz)
        app.router.add_get("/healthz", handle_healthz)
        app.router.add_get("/queue_stats", handle_queue_stats)

        # Webhook endpoint
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        ).register(app, path=WEBHOOK_PATH)

        # aiogram v3 — передаем всё, что нужно в хэндлеры, через kwargs
        setup_application(app, dp, bot=bot)

        # 🚀 Запуск сервера
        port = int(os.getenv("PORT", "10000"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site.start()

        logger.info(f"🚀 Webhook bot started on port {port}")
        logger.info(f"📍 Webhook URL: {WEBHOOK_URL}")

        # держим процесс живым
        await asyncio.Event().wait()
    except Exception as e:
        logger.critical(f"💥 Critical error in main: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
