import os
import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage  # 🔥 КРИТИЧЕСКИ ВАЖНО

from app.config import BOT_TOKEN
from app.handlers import start, menu_and_flow, fallback


WEBHOOK_PATH = "/telegram/webhook"
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "").rstrip("/")
WEBHOOK_URL = f"{PUBLIC_APP_URL}{WEBHOOK_PATH}"


async def main():
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

    # Webhook endpoint
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path=WEBHOOK_PATH)

    # aiogram v3 — ТОЛЬКО 2 аргумента
    setup_application(app, dp)

    # Устанавливаем webhook
    await bot.set_webhook(WEBHOOK_URL)

    # 🚀 Запуск сервера
    port = int(os.getenv("PORT", "10000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    print("🚀 Webhook bot started", flush=True)

    # держим процесс живым
    try:
        await asyncio.Event().wait()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
