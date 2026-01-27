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
    """
    Атомарное создание job'а с проверкой идемпотентности.
    
    Flow:
    1. Проверить, существует ли уже job с таким idempotency_key
    2. Скачать фото из Telegram
    3. Загрузить фото в storage
    4. Создать job в БД и списать кредит (RPC)
    5. Обновить job дополнительными метаданными
    6. Вернуть job_id и новый баланс
    
    Если ошибка - отправить сообщение пользователю и вернуть (None, None)
    """
    
    logger.info(f"📦 START generate: user={tg_user_id}, template={template_id}, kind={kind}")
    
    # 1) Проверить, существует ли уже job с таким idempotency key
    existing_job = await get_job_by_idempotency_key(idempotency_key)
    if existing_job:
        logger.info(f"♻️ Job already exists for key {idempotency_key}: id={existing_job['id']}")
        current_credits = await safe_get_balance(tg_user_id)
        return existing_job["id"], current_credits

    # 2) скачать фото
    logger.info(f"📥 Downloading photo from Telegram: file_id={photo_file_id[:30]}...")
    photo_bytes = await download_photo_bytes(bot, photo_file_id)
    logger.info(f"✅ Downloaded {len(photo_bytes)} bytes")

    # 3) загрузить в storage
    # ВАЖНО: путь внутри bucket БЕЗ "inputs/"
    input_path = f"{tg_user_id}/{uuid.uuid4().hex}.jpg"
    storage = get_storage()
    logger.info(f"📤 Uploading to storage: {input_path}")
    await storage.upload_input_photo(input_path, photo_bytes)
    logger.info(f"✅ Uploaded to storage")

    # 4) создать job и списать кредит атомарно
    # Конвертируем product_info в JSON string для PostgreSQL JSONB
    prompt_input_str = ensure_json_string(product_info)
    
    # 🔍 DEBUG: Логируем что передаём
    logger.info(f"🔍 DEBUG product_info dict: {product_info}")
    logger.info(f"🔍 DEBUG prompt_input_str (JSON): {prompt_input_str[:500]}")
    
    try:
        logger.info(f"📝 RPC call: create_job_and_consume_credit for user {tg_user_id}, template={template_id}")
        result = await create_job_and_consume_credit(
            tg_user_id=tg_user_id,
            template_type=kind,
            idempotency_key=idempotency_key,
            photo_path=input_path,
            prompt_input=prompt_input_str,
        )
        logger.info(f"✅ RPC result: job_id={result['job_id']}, credits={result['new_credits']}")
        job_id = result["job_id"]
        new_credits = result["new_credits"]
        
        # 5) Обновляем job с дополнительными полями для worker
        logger.info(f"📝 Updating job {job_id} with metadata...")
        
        # Строим JSON для error_details с метаданными
        import json
        metadata = {
            "template_id": template_id,
            "kind": kind,
            "user_prompt": product_info.get("user_prompt", "")
        }
        
        await update_job(str(job_id), {
            "product_image_url": input_path,
            "product_name": product_info.get("text", "")[:200],  # используем product_name
            "product_text": product_info.get("text", ""),
            "extra_wishes": extra_wishes,
            "error_details": json.dumps(metadata),  # преобразуем dict в JSON string
            "status": "queued"
        })
        
        logger.info(f"✅ Job {job_id} created and queued to database. Worker will pick it up via polling.")
        
    except Exception as e:
        # Логируем реальную ошибку с полным контекстом
        error_str = str(e)
        logger.error(f"❌ RPC failed for user {tg_user_id}: {error_str}", exc_info=True)
        
        # Определяем тип ошибки и отправляем специфичное сообщение
        if "insufficient" in error_str.lower() or "credits" in error_str.lower():
            error_msg = "❌ <b>Недостаточно кредитов.</b>\n\nПополните баланс и попробуйте снова."
            logger.warning(f"⚠️ User {tg_user_id} has insufficient credits")
        elif "duplicate" in error_str.lower():
            error_msg = "⚠️ <b>Это задание уже обрабатывается.</b>\n\nПопробуйте создать новое."
            logger.warning(f"⚠️ Duplicate key detected: {idempotency_key}")
        else:
            error_msg = f"⚠️ <b>Ошибка создания задания:</b>\n{error_str[:100]}"
            logger.warning(f"⚠️ Generic error: {error_str[:100]}")
        
        logger.info(f"📤 Sending error message to user {tg_user_id}")
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
