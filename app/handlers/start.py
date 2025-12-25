from aiogram import Router
from aiogram.types import Message
from app.keyboards import kb_continue
from app import texts
from app.db import get_or_create_user

router = Router()

@router.message()
async def start_handler(message: Message):
    if message.text and message.text.startswith("/start"):
        get_or_create_user(message.from_user.id, message.from_user.username)
        # тут позже добавишь видео-инструкцию (send_video). Пока текст + кнопка.
        await message.answer(texts.WELCOME, reply_markup=kb_continue())
