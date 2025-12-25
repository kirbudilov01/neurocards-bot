from aiogram import Router
from aiogram.types import Message, FSInputFile
from app.keyboards import kb_continue
from app import texts
from app.db import get_or_create_user

router = Router()

WELCOME_VIDEO_PATH = "assets/welcome.mp4"   # положи файл в репу
MENU_PHOTO_PATH = "assets/menu.jpg"         # положи файл в репу (или убери, если не надо)

@router.message()
async def start_handler(message: Message):
    if message.text and message.text.startswith("/start"):
        get_or_create_user(message.from_user.id, message.from_user.username)

        # 1) видео (если файла нет — просто закомментируй 2 строки)
        await message.answer_video(FSInputFile(WELCOME_VIDEO_PATH))

        # 2) приветственный текст
        await message.answer(texts.WELCOME, reply_markup=kb_continue())
