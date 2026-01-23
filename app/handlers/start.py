from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile

from app import texts
from app.keyboards import kb_continue
from app.db_adapter import get_or_create_user

router = Router()

WELCOME_VIDEO_PATH = "assets/welcome.mp4"

@router.message(CommandStart())
async def start_handler(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    
    # ✅ Check if new user (credits == 2 means just created)
    is_new_user = user.get("credits") == 2 and user.get("created_at") is not None

    try:
        await message.answer_video(FSInputFile(WELCOME_VIDEO_PATH))
    except Exception:
        pass

    # Показать приветственное сообщение с информацией о токенах
    if is_new_user:
        welcome_text = (
            "🎉 <b>Welcome to NeuroCards!</b>\n\n"
            "📺 I'll generate viral video from your products.\n\n"
            "🎁 <b>You have 2 FREE videos to try!</b>\n"
            "After that, it's paid. But the quality is insane 😎\n\n"
            "Let's create something awesome!"
        )
        await message.answer(welcome_text, parse_mode="HTML", reply_markup=kb_continue())
    else:
        await message.answer(texts.WELCOME, reply_markup=kb_continue(), parse_mode="HTML")
