from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
import logging

from app import texts
from app.keyboards import kb_continue
from app.db_adapter import get_or_create_user
from app.config import WELCOME_VIDEO_FILE_ID

router = Router()
logger = logging.getLogger(__name__)

WELCOME_VIDEO_PATH = "/app/assets/welcome.mp4"

@router.message(CommandStart())
async def start_handler(message: Message):
    logger.info(f"🎬 START command from user {message.from_user.id} (@{message.from_user.username})")
    
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    logger.info(f"✅ User retrieved: {user.get('id')}, credits: {user.get('credits')}")
    
    # ✅ Check if new user (credits == 2 means just created)
    is_new_user = user.get("credits") == 2 and user.get("created_at") is not None

    try:
        if WELCOME_VIDEO_FILE_ID:
            # Используем сохранённый file_id (мгновенная отправка)
            logger.info(f"✅ USING FILE_ID (быстро): {WELCOME_VIDEO_FILE_ID[:30]}...")
            await message.answer_video(video=WELCOME_VIDEO_FILE_ID)
            logger.info("✅ Video sent successfully via file_id (instant)")
        else:
            # Загружаем с диска (медленно! 60+ секунд)
            logger.warning(f"⚠️ WELCOME_VIDEO_FILE_ID not set! Loading from disk (slow ~60s): {WELCOME_VIDEO_PATH}")
            logger.warning(f"⚠️ To fix: export WELCOME_VIDEO_FILE_ID='<file_id>' and restart")
            msg = await message.answer_video(FSInputFile(WELCOME_VIDEO_PATH))
            logger.info(f"✅ Video sent successfully! file_id: {msg.video.file_id}")
            logger.warning(f"⚠️ SAVE THIS file_id to .env and restart:\n   WELCOME_VIDEO_FILE_ID={msg.video.file_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send video: {e}")

    # Показать приветственное сообщение
    try:
        logger.info("📝 Sending welcome text...")
        await message.answer(texts.WELCOME, reply_markup=kb_continue(), parse_mode="HTML")
        logger.info("✅ Welcome text sent successfully")
    except Exception as e:
        logger.error(f"❌ Failed to send welcome text: {e}")
