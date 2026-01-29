from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile, LinkPreviewOptions
import logging

from app import texts
from app.keyboards import kb_continue, kb_accept_terms
from app.db_adapter import get_or_create_user
from app.config import WELCOME_VIDEO_FILE_ID, WELCOME_VIDEO_FILE_IDS

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

    # Показать согласие с условиями (первое сообщение после /start)
    try:
        terms_text = (
            "Я принимаю \u003ca href=\"https://disk.yandex.ru/i/Z01zSljibnw2wg\"\u003eпользовательское соглашение и публичную оферта\u003c/a\u003e "
            "и также даю свое согласие на обработку персональных данных и принимаю "
            "\u003ca href=\"https://disk.yandex.ru/i/EgdIQo4Nhq9xog\"\u003eполитику конфиденциальности\u003c/a\u003e."
        )
        # Полностью отключаем превью ссылок (HTML anchors без превью)
        await message.answer(
            terms_text,
            reply_markup=kb_accept_terms(),
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        logger.info("✅ Terms consent message sent successfully")
    except Exception as e:
        logger.error(f"❌ Failed to send terms message: {e}")


from aiogram import F
from aiogram.types import CallbackQuery

@router.callback_query(F.data == "accept_terms")
async def on_accept_terms(cb: CallbackQuery):
    await cb.answer()

    # После принятия условий отправляем демо-видео (поддержка до 10 file_id)
    try:
        sent = 0
        ids = WELCOME_VIDEO_FILE_IDS or ([WELCOME_VIDEO_FILE_ID] if WELCOME_VIDEO_FILE_ID else [])
        if ids:
            for vid in ids[:10]:
                logger.info(f"✅ USING FILE_ID (быстро): {vid[:30]}...")
                await cb.message.answer_video(video=vid)
                sent += 1
            logger.info(f"✅ Sent {sent} demo videos via file_id (instant)")
        else:
            logger.warning(f"⚠️ WELCOME_VIDEO_FILE_ID not set! Loading from disk (slow ~60s): {WELCOME_VIDEO_PATH}")
            logger.warning(f"⚠️ To fix: export WELCOME_VIDEO_FILE_ID='<file_id>' and restart")
            msg = await cb.message.answer_video(FSInputFile(WELCOME_VIDEO_PATH))
            logger.info(f"✅ Video sent successfully! file_id: {msg.video.file_id}")
            logger.warning(
                f"⚠️ SAVE THIS file_id to .env and restart:\n   WELCOME_VIDEO_FILE_ID={msg.video.file_id}\n"
                f"   or append to WELCOME_VIDEO_FILE_IDS with commas"
            )
    except Exception as e:
        logger.error(f"❌ Failed to send video: {e}")

    # Далее отправляем приветственное сообщение с кнопкой "Продолжить"
    try:
        await cb.message.answer(getattr(texts, "WELCOME", "Добро пожаловать!"), reply_markup=kb_continue(), parse_mode="HTML")
        logger.info("✅ Welcome text sent successfully after terms acceptance")
    except Exception as e:
        logger.error(f"❌ Failed to send welcome text: {e}")
