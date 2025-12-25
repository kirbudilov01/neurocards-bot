import uuid

from app import texts
from app.keyboards import kb_no_credits, kb_started
from app.services.tg_files import download_photo_bytes
from app.services.storage import upload_input_photo
from app.db import create_job, consume_credit, get_queue_position


async def start_generation(
    bot,
    tg_user_id: int,
    photo_file_id: str,
    kind: str,
    product_info: dict,
    extra_wishes: str | None,
    template_id: str,
):
    # 1) скачать фото
    photo_bytes = await download_photo_bytes(bot, photo_file_id)

    # 2) загрузить в storage
    # ВАЖНО: путь внутри bucket БЕЗ "inputs/"
    input_path = f"{tg_user_id}/{uuid.uuid4().hex}.jpg"
    upload_input_photo(input_path, photo_bytes)

    # 3) создать job
    job = create_job(
        tg_user_id=tg_user_id,
        kind=kind,
        input_photo_path=input_path,
        product_info=product_info,
        extra_wishes=extra_wishes,
        template_id=template_id,
    )

    # 4) списать кредит атомарно
    try:
        new_credits = consume_credit(tg_user_id, job["id"])
    except Exception:
        # если кредит списать не удалось (например, не хватает)
        await bot.send_message(
            tg_user_id,
            getattr(texts, "NO_CREDITS", "❌ Недостаточно кредитов. Пополни баланс в личном кабинете."),
            reply_markup=kb_no_credits(),
            parse_mode="HTML",
        )
        # чтобы вызывающий код не падал
        return None, None

    # 5) (опционально) считаем позицию, но НЕ шлём отдельным сообщением
    # оставим на будущее: можно дописать в текст, если захочешь
    try:
        _ = get_queue_position(job["id"])
    except Exception:
        pass

    # 6) одно красивое сообщение “генерация запущена” + баланс + кнопки
    started_tpl = getattr(
        texts,
        "GENERATION_STARTED",
        "Генерация запущена. Баланс: {credits}",
    )
    await bot.send_message(
        tg_user_id,
        started_tpl.format(credits=new_credits),
        reply_markup=kb_started(kind),
        parse_mode="HTML",
    )

    return job["id"], new_credits
