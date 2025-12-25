import asyncio
import json
import os
import re
from datetime import datetime, timezone

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile
from supabase import create_client

from worker.kie_client import create_task_sora_i2v, poll_record_info
from worker.openai_prompter import build_prompt_with_gpt
from worker.prompt_templates import REELS_UGC_TEMPLATE_V1


def req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v.strip()


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
    pub = supabase.storage.from_("inputs").get_public_url(input_path)
    if isinstance(pub, dict):
        return pub.get("publicUrl") or pub.get("public_url") or str(pub)
    return str(pub)


def find_first_mp4_url(obj):
    url_re = re.compile(r"https?://[^\s\"']+\.mp4(\?[^\s\"']+)?", re.IGNORECASE)

    if obj is None:
        return None
    if isinstance(obj, str):
        m = url_re.search(obj)
        return m.group(0) if m else None
    if isinstance(obj, dict):
        for v in obj.values():
            found = find_first_mp4_url(v)
            if found:
                return found
    if isinstance(obj, list):
        for it in obj:
            found = find_first_mp4_url(it)
            if found:
                return found
    return None


async def download_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


async def main():
    print("WORKER: started main loop")
    bot = Bot(BOT_TOKEN)

    while True:
        job = fetch_next_queued_job()
        if not job:
            await asyncio.sleep(2)
            continue

        job_id = job["id"]
        user = get_user_by_id(job["user_id"])
        if not user:
            update_job(job_id, {"status": "failed", "error": "user_not_found", "finished_at": now_iso()})
            continue

        tg_user_id = user["tg_user_id"]

        try:
            update_job(job_id, {"status": "processing", "started_at": now_iso()})

            if job.get("kind") != "reels":
                raise RuntimeError("Only reels supported (demo)")

            input_path = job.get("input_photo_path")
            if not input_path:
                raise RuntimeError("Missing input_photo_path")

            image_url = get_public_input_url(input_path)

            script = build_prompt_with_gpt(
                system=REELS_UGC_TEMPLATE_V1["system"],
                instructions=REELS_UGC_TEMPLATE_V1["instructions"],
                product_text=(job.get("product_info") or {}).get("text", ""),
                extra_wishes=job.get("extra_wishes"),
            )

            task_id = create_task_sora_i2v(prompt=script, image_url=image_url)
            if not task_id:
                raise RuntimeError("KIE: could not extract task_id")

            await bot.send_message(tg_user_id, "🎬 Генерация запущена. Жду до 5 минут и пришлю результат.")

            info = poll_record_info(task_id, timeout_sec=300, interval_sec=10)

            print("\n==== KIE recordInfo raw ====")
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("==== /KIE recordInfo raw ====\n")

            mp4_url = find_first_mp4_url(info)
            if not mp4_url:
                update_job(job_id, {"status": "failed", "error": "no_mp4_url", "finished_at": now_iso()})
                await bot.send_message(tg_user_id, "❌ Не нашёл mp4 в ответе KIE (JSON в логах воркера).")
                continue

            data = await download_bytes(mp4_url)

            max_bytes = 45 * 1024 * 1024
            if len(data) > max_bytes:
                update_job(job_id, {"status": "done", "finished_at": now_iso(), "output_url": mp4_url})
                await bot.send_message(tg_user_id, f"✅ Видео готово! Ссылка:\n{mp4_url}")
            else:
                await bot.send_video(tg_user_id, video=BufferedInputFile(data, filename="reels.mp4"), caption="✅ Готово!")
                update_job(job_id, {"status": "done", "finished_at": now_iso(), "output_url": mp4_url})

        except Exception as e:
            print("WORKER_ERROR:", repr(e))
            update_job(job_id, {"status": "failed", "error": str(e), "finished_at": now_iso()})
            try:
                await bot.send_message(tg_user_id, f"❌ Ошибка генерации:\n{e}")
            except Exception:
                pass

        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
