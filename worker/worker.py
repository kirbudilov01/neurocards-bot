import asyncio
import json
import os
from datetime import datetime, timezone

from aiogram import Bot
from supabase import create_client

from worker.openai_prompter import build_prompt_with_gpt
from worker.prompt_templates import REELS_UGC_TEMPLATE_V1
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
    Kie ждёт image_urls (URL на картинку).
    Для v1 предполагаем, что bucket inputs — Public.
    """
    pub = supabase.storage.from_("inputs").get_public_url(input_path)
    if isinstance(pub, dict):
        return pub.get("publicUrl") or pub.get("publicURL") or pub.get("public_url") or str(pub)
    return str(pub)


async def main():
    bot = Bot(BOT_TOKEN)
    print("Worker started (Kie v1 reels).")

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

            kind = job["kind"]
            if kind != "reels":
                # Пока делаем только reels (чисто и без лишнего)
                update_job(job_id, {"status": "failed", "error": "only_reels_supported_v1", "finished_at": now_iso()})
                await bot.send_message(tg_user_id, "Пока поддерживается только 🎬 REELS. Нейрокарточки подключим позже.")
                await asyncio.sleep(1)
                continue

            product_text = (job.get("product_info") or {}).get("text", "")
            extra_wishes = job.get("extra_wishes")

            # 1) Публичный URL на фото товара (Kie image_urls)
            input_url = get_public_input_url(job["input_photo_path"])

            # 2) GPT пишет сценарий + мини-промпт (по твоей логике)
            tpl = REELS_UGC_TEMPLATE_V1
            script_and_prompt = build_prompt_with_gpt(
                system=tpl["system"],
                instructions=tpl["instructions"],
                product_text=product_text,
                extra_wishes=extra_wishes,
            )

            # 3) В Kie мы отправляем мини-промпт (пока без парсинга — отправим весь блок, Kie проглотит как текст)
            # На следующем шаге, когда увидим формат, вытащим именно "🤖 Мини-промпт..."
            kie_prompt = script_and_prompt

            task_id = create_task_sora_i2v(prompt=kie_prompt, image_url=input_url)

            await bot.send_message(
                tg_user_id,
                "✅ Сценарий и промпт собраны и отправлены в генерацию.\n"
                "⏳ Ожидай 3–5 минут. Я пришлю результат."
            )

            # 4) recordInfo — логируем сырой ответ (чтобы понять, где ссылка на mp4)
            info = poll_record_info(task_id)

            print("\n==== KIE recordInfo raw ====")
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("==== /KIE recordInfo raw ====\n")

            update_job(job_id, {
                "status": "done",
                "finished_at": now_iso(),
                "kie_task_id": task_id,
            })

            await bot.send_message(
                tg_user_id,
                "🧩 Я получил ответ от Kie.\n"
                "Сейчас в логах воркера есть JSON — по нему в следующем шаге я достану ссылку на mp4 "
                "и мы начнём автоматически присылать видео."
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
