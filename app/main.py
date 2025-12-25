import asyncio
import os
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.config import BOT_TOKEN
from app.handlers import start, menu_and_flow, fallback


WEBHOOK_PATH = "/telegram/webhook"
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
WEBHOOK_URL = f"{PUBLIC_APP_URL}{WEBHOOK_PATH}"


async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    # регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(menu_and_flow.router)
    dp.include_router(fallback.router)  # всегда последним

    # webhook
    await bot.set_webhook(WEBHOOK_URL)

    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot)

    # Render сам подставляет PORT
    port = int(os.getenv("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    print("🚀 Bot started with webhook")
    # ВАЖНО: ничего не return, просто держим процесс
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
