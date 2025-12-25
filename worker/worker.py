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


def normalize_storage_path(input_path: str) -> str:
    """
    Делаем путь ОТНОСИТЕЛЬНЫМ внутри bucket 'inputs':
    - было: 'inputs/523/...jpg' -> станет '523/...jpg'
    - было: '/inputs/523/...jpg' -> станет '523/...jpg'
    - было: '523/...jpg' -> остаётся так
    """
    p = (input_path or "").strip().lstrip("/")
    if p.startswith("inputs/"):
        p = p[len("inputs/"):]
    return p


def get_public_input_url(input_path: str) -> str:
    rel = normalize_storage_path(input_path)

    pub = supabase.storage.from_("inputs").get_public_url(rel)
    if isinstance(pub, dict):
        return pub.get("publicUrl") or pub.get("public_url") or str(pub)
    return str(pub)


def find_video_url(obj):
    """
    Универсально ищет ссылку на видео (mp4/mov/webm/m3u8) или типичные url-поля.
    """
    common_keys = {
        "video", "video_url", "videoUrl", "output_url", "outputUrl",
        "url", "download_url", "downloadUrl", "file_url", "fileUrl",
        "result_url", "resultUrl", "play_url", "playUrl"
    }

    if obj is None:
        return None

    if isinstance(obj, dict):
        # сначала по ключам
        for k, v in obj.items():
            if k in common_keys and isinstance(v, str) and v.startswith("http"):
                return v
        # потом глубже
        for v in obj.values():
            got = find_video_url(v)
            if got:
                return got

    if isinstance(obj, list):
        for it in obj:
            got = find_video_url(it)
            if got:
                return got

    if isinstance(obj, str):
        m = re.search(r"https?://[^\s\"']+\.(mp4|mov|webm|m3u8)(\?[^\s\"']+)?", obj, re.I)
        if m:
            return m.group(0)

    return None


def extract_fail_message(info: dict) -> str | None:
    """
    Достаём failMsg если KIE вернул fail.
    """
    try:
        data = info.get("data") if isinstance(info, dict) else None
        if isinstance(data, dict):
            state = (data.get("state") or data.get("status") or "").lower()
            if state == "fail" or state == "failed":
                return data.get("failMsg") or data.get("message") or "KIE failed"
    except Exception:
        pass
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

            # можно залогировать, чтобы сразу видеть что URL без inputs/inputs
            print("INPUT_PATH:", input_path)
            print("IMAGE_URL:", image_url)

            script = build_prompt_with_gpt(
                system=REELS_UGC_TEMPLATE_V1["system"],
                instructions=REELS_UGC_TEMPLATE_V1["instructions"],
                product_text=(job.get("product_info") or {}).get("text", ""),
                extra_wishes=job.get("extra_wishes"),
            )

            task_id = create_task_sora_i2v(prompt=script, image_url=image_url)
            if not task_id:
                raise RuntimeError("KIE: could not extract task_id")

            # если колонка есть — сохраним
            try:
                update_job(job_id, {"kie_task_id": task_id})
            except Exception:
                pass

            await bot.send_message(tg_user_id, "🎬 Генерация запущена. Жду до 5 минут и пришлю результат.")

            # ⚠️ poll_record_info блокирующий (time.sleep внутри),
            # поэтому выполняем его в отдельном потоке, чтобы не душить event loop
            info = await asyncio.to_thread(poll_record_info, task_id, 300, 10)

            print("\n==== KIE recordInfo raw ====")
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("==== /KIE recordInfo raw ====\n")

            fail_msg = extract_fail_message(info)
            if fail_msg:
                update_job(job_id, {"status": "failed", "error": fail_msg, "finished_at": now_iso()})
                await bot.send_message(
                    tg_user_id,
                    f"❌ KIE не смог обработать изображение/задачу.\nПричина: {fail_msg}"
                )
                continue

            video_url = find_video_url(info)
            if not video_url:
                update_job(job_id, {"status": "failed", "error": "no_video_url", "finished_at": now_iso()})
                await bot.send_message(
                    tg_user_id,
                    "❌ Я дождался ответа KIE, но не нашёл ссылку на видео.\n"
                    "JSON ответа сохранён в логах воркера — поправим парсер."
                )
                continue

            data = await download_bytes(video_url)

            # безопасный лимит, чтобы не ловить проблемы Telegram
            max_bytes = 45 * 1024 * 1024
            if len(data) > max_bytes:
                update_job(job_id, {"status": "done", "finished_at": now_iso(), "output_url": video_url})
                await bot.send_message(tg_user_id, f"✅ Видео готово! Ссылка:\n{video_url}")
            else:
                await bot.send_video(
                    tg_user_id,
                    video=BufferedInputFile(data, filename="reels.mp4"),
                    caption="✅ Готово!"
                )
                update_job(job_id, {"status": "done", "finished_at": now_iso(), "output_url": video_url})

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
