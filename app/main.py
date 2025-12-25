import os
import asyncio
import traceback

from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.config import BOT_TOKEN
from app.handlers import start, menu_and_flow, fallback

WEBHOOK_PATH = "/telegram/webhook"
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
WEBHOOK_URL = f"{PUBLIC_APP_URL}{WEBHOOK_PATH}"


async def on_startup(bot: Bot):
    # выставляем webhook на URL твоего web service
    await bot.set_webhook(WEBHOOK_URL)


async def on_shutdown(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()


def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    # ✅ подключаем роутеры ПОСЛЕ создания dp
    dp.include_router(start.router)
    dp.include_router(menu_and_flow.router)
    dp.include_router(fallback.router)  # последним

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("WORKER_FATAL_ERROR:\n", traceback.format_exc(), flush=True)
        # чтобы Render не устраивал "дребезг" рестартов
        while True:
            time.sleep(60)
