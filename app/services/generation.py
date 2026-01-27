import logging
import uuid
import json

from app import texts
from app.keyboards import kb_no_credits, kb_started
from app.services.tg_files import download_photo_bytes
from app.services.storage_factory import get_storage
from app.db_adapter import get_job_by_idempotency_key, create_job_and_consume_credit, safe_get_balance, update_job
from app.utils import ensure_json_string

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
    # Конвертируем product_info в JSON string для PostgreSQL JSONB
    prompt_input_str = ensure_json_string(product_info)
    
    try:
        logger.info(f"📝 Calling RPC: create_job_and_consume_credit for user {tg_user_id}, key={idempotency_key[:20]}...")
        result = await create_job_and_consume_credit(
            tg_user_id=tg_user_id,
            template_type=kind,
            idempotency_key=idempotency_key,
            photo_path=input_path,
            prompt_input=prompt_input_str,
        )
        logger.info(f"✅ RPC returned: {result}")
        job_id = result["job_id"]
        new_credits = result["new_credits"]
        
        # 5) Обновляем job с дополнительными полями для worker
        logger.info(f"📝 Updating job {job_id} with queue status...")
        await update_job(str(job_id), {
            "product_image_url": input_path,
            "product_info": product_info,  # dict для PostgreSQL JSONB
            "template_id": template_id,
            "extra_wishes": extra_wishes,
            "kind": kind,
            "status": "queued"
        })
        
        logger.info(f"✅ Job {job_id} created and added to PostgreSQL queue")
        
    except Exception as e:
        # Логируем реальную ошибку с полным контекстом
        error_str = str(e)
        logger.error(f"❌ Failed to create job for user {tg_user_id}: {error_str}", exc_info=True)
        
        # Определяем тип ошибки и отправляем специфичное сообщение
        if "insufficient" in error_str.lower() or "credits" in error_str.lower():
            error_msg = "❌ <b>Недостаточно кредитов.</b>\n\nПополните баланс и попробуйте снова."
        elif "duplicate" in error_str.lower():
            error_msg = "⚠️ <b>Это задание уже обрабатывается.</b>\n\nПопробуйте создать новое."
        else:
            error_msg = f"⚠️ <b>Ошибка создания задания:</b>\n{error_str[:100]}"
        
        await bot.send_message(
            tg_user_id,
            error_msg,
            reply_markup=kb_no_credits(),
            parse_mode="HTML",
        )
        # чтобы вызывающий код не падал
        return None, None

    # НЕ отправляем уведомление здесь - worker отправит его сам

    return job_id, new_credits
