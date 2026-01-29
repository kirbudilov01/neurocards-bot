from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile, LinkPreviewOptions, InputMediaVideo
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
            disable_web_page_preview=True,
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
        ids = WELCOME_VIDEO_FILE_IDS or ([WELCOME_VIDEO_FILE_ID] if WELCOME_VIDEO_FILE_ID else [])
        if ids:
            media = [InputMediaVideo(media=vid) for vid in ids[:10]]
            if len(media) == 1:
                logger.info(f"✅ USING single FILE_ID (быстро): {ids[0][:30]}...")
                await cb.message.answer_video(video=ids[0])
            else:
                logger.info(f"✅ Sending media group of {len(media)} videos via file_id (instant)")
                await cb.message.answer_media_group(media)
        else:
            # НЕТ fallback с диска — пропускаем отправку видео
            logger.info("ℹ️ No welcome video IDs configured; skipping demo videos.")
    except Exception as e:
        logger.error(f"❌ Failed to send video: {e}")

    # Далее отправляем приветственное сообщение с кнопкой "Продолжить"
    try:
        await cb.message.answer(getattr(texts, "WELCOME", "Добро пожаловать!"), reply_markup=kb_continue(), parse_mode="HTML")
        logger.info("✅ Welcome text sent successfully after terms acceptance")
    except Exception as e:
        logger.error(f"❌ Failed to send welcome text: {e}")
