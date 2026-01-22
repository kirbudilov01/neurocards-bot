import logging
import uuid

from app import texts
from app.keyboards import kb_no_credits, kb_started
from app.services.tg_files import download_photo_bytes
from app.services.storage_factory import get_storage
from app.db_adapter import get_job_by_idempotency_key, create_job_and_consume_credit, get_queue_position, safe_get_balance

logger = logging.getLogger(__name__)


async def start_generation(
    bot,
    tg_user_id: int,
    idempotency_key: str,
    photo_file_id: str,
    kind: str,
    product_info: dict,
    extra_wishes: str | None,
    template_id: str,
):
    # 1) Проверить, существует ли уже job с таким idempotency key
    existing_job = await get_job_by_idempotency_key(idempotency_key)
    if existing_job:
        # Если job уже существует, вернуть его ID и текущий баланс пользователя
        current_credits = await safe_get_balance(tg_user_id)
        return existing_job["id"], current_credits

    # 2) скачать фото
    photo_bytes = await download_photo_bytes(bot, photo_file_id)

    # 3) загрузить в storage
    # ВАЖНО: путь внутри bucket БЕЗ "inputs/"
    input_path = f"{tg_user_id}/{uuid.uuid4().hex}.jpg"
    storage = get_storage()
    await storage.upload_input_photo(input_path, photo_bytes)

    # 4) создать job и списать кредит атомарно
    try:
        result = await create_job_and_consume_credit(
            tg_user_id=tg_user_id,
            template_type=kind,
            idempotency_key=idempotency_key,
            photo_path=input_path,
            prompt_input=product_info,
        )
        job_id = result["job_id"]
        new_credits = result["new_credits"]
    except Exception as e:
        # Логируем реальную ошибку
        logger.error(f"❌ Failed to create job: {e}", exc_info=True)
        
        # если RPC упал (например, 'Not enough credits'), сообщим об этом
        await bot.send_message(
            tg_user_id,
            getattr(texts, "ERROR_GENERATION", "⚠️ Ошибка, попробуй ещё раз"),
            reply_markup=kb_no_credits(),
            parse_mode="HTML",
        )
        # чтобы вызывающий код не падал
        return None, None

    # 4) (опционально) считаем позицию, но НЕ шлём отдельным сообщением
    try:
        _ = await get_queue_position(job_id)
    except Exception:
        pass

    # НЕ отправляем уведомление здесь - worker отправит его сам

    return job_id, new_credits
