import asyncio
import json
import os
from datetime import datetime, timezone

from aiogram import Bot
from supabase import create_client

from worker.openai_prompter import build_prompt_with_gpt
from worker.prompt_templates import REELS_TEMPLATE_1, NEUROCARD_TEMPLATE_1
from worker.kie_client import create_task_sora_i2v, poll_record_info


def req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

BOT_TOKEN = req("BOT_TOKEN")
SUPABASE_URL = req("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = req("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def fetch_next_queued_job():
    res = (
        supabase.table("jobs")
        .select("*")
        .eq("status", "queued")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None

def update_job(job_id: str, patch: dict):
    supabase.table("jobs").update(patch).eq("id", job_id).execute()

def get_user_by_id(user_id: str):
    res = supabase.table("users").select("*").eq("id", user_id).limit(1).execute()
    return res.data[0] if res.data else None

def get_public_input_url(input_path: str) -> str:
    """
    ВАЖНО: Kie принимает image_urls.
    Самый простой v1: требуем, чтобы inputs bucket был Public,
    и берём публичный URL.
    """
    pub = supabase.storage.from_("inputs").get_public_url(input_path)
    # библиотека может вернуть dict или строку — нормализуем
    if isinstance(pub, dict):
        return pub.get("publicUrl") or pub.get("publicURL") or pub.get("public_url") or str(pub)
    return str(pub)

async def main():
    bot = Bot(BOT_TOKEN)
    print("Worker started (Kie v1).")

    while True:
        job = fetch_next_queued_job()
        if not job:
            await asyncio.sleep(2)
            continue

        job_id = job["id"]
        user = get_user_by_id(job["user_id"])
        if not user:
            update_job(job_id, {"status": "failed", "error": "user_not_found", "finished_at": now_iso()})
            await asyncio.sleep(1)
            continue

        tg_user_id = user["tg_user_id"]

        try:
            update_job(job_id, {"status": "processing", "started_at": now_iso()})

            kind = job["kind"]              # "reels" или "neurocard"
            product_text = (job.get("product_info") or {}).get("text", "")
            extra_wishes = job.get("extra_wishes")
            template_id = job.get("template_id") or "template_1"

            # 1) public URL на входное фото (Kie ждёт image_urls)
            input_url = get_public_input_url(job["input_photo_path"])

            # 2) GPT -> prompt
            if kind == "reels":
                tpl = REELS_TEMPLATE_1
            else:
                tpl = NEUROCARD_TEMPLATE_1

            prompt = build_prompt_with_gpt(
                system=tpl["system"],
                instructions=tpl["instructions"],
                product_text=product_text,
                extra_wishes=extra_wishes,
            )

            # 3) Kie createTask (в v1 используем sora-2-image-to-video для reels)
            # Для neurocard позже подставим другую модель Kie, когда ты скажешь какую.
            task_id = create_task_sora_i2v(prompt=prompt, image_url=input_url)

            await bot.send_message(
                tg_user_id,
                "✅ Промпт собран и отправлен в генерацию.\n"
                "⏳ Ожидай 3–5 минут. Я пришлю результат."
            )

            # 4) recordInfo — логируем ответ целиком, чтобы понять где лежит resultJson/video_url
            info = poll_record_info(task_id)

            print("\n==== KIE recordInfo raw ====")
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("==== /KIE recordInfo raw ====\n")

            # v1: считаем успехом, что мы дошли до ответа
            update_job(job_id, {
                "status": "done",
                "finished_at": now_iso(),
                "kie_task_id": task_id,
            })

            await bot.send_message(
                tg_user_id,
                "🧩 Я получил ответ от Kie (пока без авто-выкачивания файла).\n"
                "Сейчас в логах воркера лежит JSON — по нему я в следующем шаге достану ссылку на mp4/png."
            )

        except Exception as e:
            update_job(job_id, {"status": "failed", "error": str(e), "finished_at": now_iso()})
            try:
                await bot.send_message(tg_user_id, f"❌ Ошибка генерации: {e}")
            except:
                pass

        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
