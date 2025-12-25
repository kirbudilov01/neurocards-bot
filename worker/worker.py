import asyncio
import uuid
from aiogram import Bot
from app.config import BOT_TOKEN
from app.db import fetch_next_queued_job, update_job_status, get_user_by_id
from app.services.storage import upload_output_file, get_public_url
from app.config import SUPABASE_BUCKET_OUTPUTS

async def fake_generate(kind: str) -> tuple[bytes, str]:
    """
    Заглушка: возвращаем текстовый файл как "результат".
    Потом заменим на реальную генерацию mp4/png.
    """
    content = f"RESULT for kind={kind}\n".encode("utf-8")
    return content, "text/plain"

async def worker_loop():
    bot = Bot(BOT_TOKEN)

    while True:
        job = fetch_next_queued_job()
        if not job:
            await asyncio.sleep(2)
            continue

        job_id = job["id"]
        try:
            update_job_status(job_id, "processing", started_at="now()")

            # генерим
            data, content_type = await fake_generate(job["kind"])

            # грузим результат
            out_name = f"{job['user_id']}/{uuid.uuid4().hex}.txt"
            out_path = f"outputs/{out_name}"
            upload_output_file(out_path, data, content_type=content_type)

            # ссылка (если outputs public)
            url = get_public_url(SUPABASE_BUCKET_OUTPUTS, out_path)

            update_job_status(job_id, "done", result_url=url, finished_at="now()")

            # отправляем в телегу
            user = get_user_by_id(job["user_id"])
            await bot.send_message(
                user["tg_user_id"],
                f"✅ Готово!\n{url}\n\nХочешь сделать ещё?",
            )

        except Exception as e:
            update_job_status(job_id, "failed", error=str(e), finished_at="now()")
            # можно уведомить пользователя, если достанем tg_user_id (по user_id)
            try:
                user = get_user_by_id(job["user_id"])
                await bot.send_message(user["tg_user_id"], f"❌ Ошибка генерации: {e}")
            except:
                pass

        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(worker_loop())
