import os
import asyncio
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

    dp.include_router(start.router)
    dp.include_router(menu_and_flow.router)
    dp.include_router(fallback.router)  # обязательно последним

    app = web.Application()

    # Регистрируем webhook endpoint
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    # ВАЖНО: в твоей версии aiogram тут только 2 аргумента
    setup_application(app, dp)

    # Ставим webhook
    await bot.set_webhook(WEBHOOK_URL)

    port = int(os.getenv("PORT", "10000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    print("🚀 Webhook bot started", flush=True)

    try:
        await asyncio.Event().wait()  # держим процесс
    finally:
        # аккуратно закрываем сессию (чтобы не было Unclosed client session)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
