from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile

from app import texts
from app.keyboards import kb_continue
from app.db import get_or_create_user

router = Router()

WELCOME_VIDEO_PATH = "assets/welcome.mp4"

@router.message(CommandStart())
async def start_handler(message: Message):
    await get_or_create_user(message.from_user.id, message.from_user.username)

    try:
        await message.answer_video(FSInputFile(WELCOME_VIDEO_PATH))
    except Exception:
        pass

    await message.answer(texts.WELCOME, reply_markup=kb_continue(), parse_mode="HTML")
