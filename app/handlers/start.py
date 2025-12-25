from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.keyboards import kb_continue
from app import texts
from app.db import get_or_create_user

router = Router()

@router.message(CommandStart())
async def start_handler(message: Message):
    get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(texts.WELCOME, reply_markup=kb_continue())
