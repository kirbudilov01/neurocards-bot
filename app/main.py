import os
import asyncio
import structlog
from aiohttp import web

from app.logging_config import setup_logging
from app.sentry_config import setup_sentry
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage  # 🔥 КРИТИЧЕСКИ ВАЖНО

from app.config import BOT_TOKEN, PUBLIC_BASE_URL
from app.handlers import start, menu_and_flow, fallback


WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = f"{PUBLIC_BASE_URL.rstrip('/')}{WEBHOOK_PATH}"


from app.config import BOT_TOKEN, WEBHOOK_SECRET_TOKEN

async def on_startup(app):
    """
    Действия при запуске:
    - Устанавливаем webhook
    """
    bot = app["bot"]
    await bot.set_webhook(
        WEBHOOK_URL,
        drop_pending_updates=True,
        secret_token=WEBHOOK_SECRET_TOKEN,
    )


async def on_shutdown(app):
    """
    Действия при выключении:
    - Удаляем webhook
    - Закрываем сессию
    """
    bot = app["bot"]
    await bot.delete_webhook()
    await bot.session.close()


async def handle_healthz(request):
    return web.Response(text="ok")


async def main():
    setup_logging()
    setup_sentry()
    log = structlog.get_logger()

    # 🔑 Бот
    bot = Bot(BOT_TOKEN)

    # ✅ FSM будет РАБОТАТЬ
    dp = Dispatcher(storage=MemoryStorage())

    # 📦 Роутеры (порядок важен)
    dp.include_router(start.router)
    dp.include_router(menu_and_flow.router)
    dp.include_router(fallback.router)  # ВСЕГДА ПОСЛЕДНИМ

    # 🌐 Web app
    app = web.Application()
    app["bot"] = bot

    # Health check endpoints
    app.router.add_get("/", handle_healthz)
    app.router.add_get("/healthz", handle_healthz)

    # 📞 Вешаем startup/shutdown обработчики
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

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

    log.info("🚀 Webhook bot started")

    # держим процесс живым
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
