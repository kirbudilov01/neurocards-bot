import logging
from aiogram import Router, F
from aiogram.types import Message

from app.config import ADMIN_IDS

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    try:
        return bool(ADMIN_IDS) and (user_id in ADMIN_IDS)
    except Exception:
        return False


@router.message(F.video)
async def echo_video_file_id(message: Message):
    """
    Админ-хэндлер: присланы видео -> отвечаем его file_id, чтобы добавить в .env.
    Если ADMIN_IDS пуст, хэндлер не активен.
    """
    uid = message.from_user.id
    if not _is_admin(uid):
        # Не спамим обычным пользователям
        return

    vid = message.video
    details = (
        f"🔑 file_id: <code>{vid.file_id}</code>\n"
        f"🆔 file_unique_id: <code>{vid.file_unique_id}</code>\n"
        f"⏱️ duration: {getattr(vid, 'duration', 'n/a')}s\n"
        f"📦 size: {getattr(vid, 'file_size', 'n/a')}\n"
        f"📐 width×height: {getattr(vid, 'width', 'n/a')}×{getattr(vid, 'height', 'n/a')}\n"
    )
    logger.info(f"📎 Received demo video from admin {uid}, file_id={vid.file_id}")
    await message.reply(
        "✅ Сохрани этот идентификатор в .env:\n"
        "WELCOME_VIDEO_FILE_IDS=\"" + vid.file_id + "\"\n\n" + details,
        parse_mode="HTML",
    )
