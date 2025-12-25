import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.config import BOT_TOKEN

from app.handlers import start, menu_and_flow, fallback

WEBHOOK_PATH = "/telegram/webhook"
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
WEBHOOK_URL = f"{PUBLIC_APP_URL}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)

async def on_startup(bot: Bot):
    if not PUBLIC_APP_URL:
        raise RuntimeError("Missing env var: PUBLIC_APP_URL")

    # Сброс старого webhook/polling и установка нового
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=False)

def build_app() -> web.Application:
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(menu_and_flow.router)
    dp.include_router(fallback.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    return app

if __name__ == "__main__":
    app = build_app()
    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)
