import uuid

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
    name = f"{tg_user_id}/{uuid.uuid4().hex}.jpg"

    # ВАЖНО: path внутри bucket БЕЗ префикса "inputs/"
    input_path = name
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
    new_credits = consume_credit(tg_user_id, job["id"])

    # 5) позиция в очереди (после постановки в jobs)
    queue_pos = get_queue_position(job["id"])

    return job["id"], new_credits, queue_pos
