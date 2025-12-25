import time
import traceback
import asyncio
import json
import os
import re
from datetime import datetime, timezone

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
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
SUPABASE_URL = req("SUPABASE_URL").rstrip("/") + "/"
SUPABASE_SERVICE_ROLE_KEY = req("SUPABASE_SERVICE_ROLE_KEY")
INPUTS_BUCKET = (os.getenv("SUPABASE_BUCKET_INPUTS") or "inputs").strip()

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kb_result(kind: str = "reels") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Сгенерировать ещё видео", callback_data=f"again:{kind}")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


def refund_credit(tg_user_id: int, amount: int = 1):
    # RPC из твоего SQL шага
    supabase.rpc("refund_credit", {"p_tg_user_id": tg_user_id, "p_amount": amount}).execute()


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


def normalize_storage_path(path: str) -> str:
    p = (path or "").strip().lstrip("/")
    # убираем любые лишние inputs/ в начале (на случай старых записей)
    while p.startswith("inputs/"):
        p = p[len("inputs/"):]
    return p


def get_public_input_url(input_path: str) -> str:
    rel = normalize_storage_path(input_path)
    pub = supabase.storage.from_(INPUTS_BUCKET).get_public_url(rel)
    if isinstance(pub, dict):
        return pub.get("publicUrl") or pub.get("public_url") or str(pub)
    return str(pub)


def extract_fail_message(info: dict) -> str | None:
    try:
        data = info.get("data") if isinstance(info, dict) else None
        if isinstance(data, dict):
            state = (data.get("state") or data.get("status") or "").lower()
            if state in {"fail", "failed", "error"}:
                return data.get("failMsg") or data.get("message") or "KIE failed"
    except Exception:
        pass
    return None


def find_video_url(obj):
    common_keys = {
        "video", "video_url", "videoUrl", "output_url", "outputUrl",
        "url", "download_url", "downloadUrl", "file_url", "fileUrl",
        "result_url", "resultUrl", "play_url", "playUrl"
    }

    if obj is None:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in common_keys and isinstance(v, str) and v.startswith("http"):
                return v
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
            await asyncio.sleep(1)
            continue

        tg_user_id = int(user["tg_user_id"])

        try:
            attempts = int(job.get("attempts") or 0) + 1
            update_job(job_id, {"status": "processing", "started_at": now_iso(), "attempts": attempts})

            kind = job.get("kind") or "reels"
            if kind not in ("reels", "neurocard"):
                # неизвестный тип — возвращаем кредит и падаем
                refund_credit(tg_user_id, 1)
                update_job(job_id, {"status": "failed", "error": "kind_not_supported", "finished_at": now_iso()})
                await bot.send_message(
                    tg_user_id,
                    "❌ Неизвестный тип генерации. Баланс восстановлен ✅",
                    reply_markup=kb_result("reels"),
                )
                await asyncio.sleep(1)
                continue

            input_path = job.get("input_photo_path")
            if not input_path:
                raise RuntimeError("Missing input_photo_path")

            image_url = get_public_input_url(input_path)
            print("IMAGE_URL:", image_url)

            product_text = (job.get("product_info") or {}).get("text", "")
            extra_wishes = job.get("extra_wishes")

            script = build_prompt_with_gpt(
                system=REELS_UGC_TEMPLATE_V1["system"],
                instructions=REELS_UGC_TEMPLATE_V1["instructions"],
                product_text=product_text,
                extra_wishes=extra_wishes,
            )

            task_id = create_task_sora_i2v(prompt=script, image_url=image_url)
            if not task_id:
                raise RuntimeError("KIE: could not extract task_id")

            update_job(job_id, {"kie_task_id": task_id})

            await bot.send_message(tg_user_id, "🎬 Генерация запущена. Пока вы ожидаете около 5 минут, можете заказать создание еще одного видео.")

            # poll_record_info блокирует (time.sleep), поэтому в thread
            info = await asyncio.to_thread(poll_record_info, task_id, 300, 10)

            print("\n==== KIE recordInfo raw ====")
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("==== /KIE recordInfo raw ====\n")

            fail_msg = extract_fail_message(info)
            if fail_msg:
                refund_credit(tg_user_id, 1)
                update_job(job_id, {"status": "failed", "error": fail_msg, "finished_at": now_iso()})
                await bot.send_message(
                    tg_user_id,
                    f"❌ Ошибка генерации. 1 кредит вернули наш баланс ✅\nПричина: {fail_msg}",
                    reply_markup=kb_result("reels"),
                )
                await asyncio.sleep(1)
                continue

            video_url = find_video_url(info)
            if not video_url:
                refund_credit(tg_user_id, 1)
                update_job(job_id, {"status": "failed", "error": "no_video_url", "finished_at": now_iso()})
                await bot.send_message(
                    tg_user_id,
                    "❌ Я дождался ответа KIE, но не нашёл ссылку на видео. Кредит вернул ✅",
                    reply_markup=kb_result("reels"),
                )
                await asyncio.sleep(1)
                continue

            data = await download_bytes(video_url)

            max_bytes = 45 * 1024 * 1024
            if len(data) > max_bytes:
                update_job(job_id, {"status": "done", "finished_at": now_iso(), "output_url": video_url})
                await bot.send_message(
                    tg_user_id,
                    f"✅ Ваше видео готово! Ссылка на скачивание:\n{video_url}",
                    reply_markup=kb_result("reels"),
                )
            else:
                await bot.send_video(
                    tg_user_id,
                    video=BufferedInputFile(data, filename="reels.mp4"),
                    caption="✅ Ваше видео готово! Не забудьте поделиться этим ботом с друзьями, чтобы получить бесплатные кредиты.",
                    reply_markup=kb_result("reels"),
                )
                update_job(job_id, {"status": "done", "finished_at": now_iso(), "output_url": video_url})

        except Exception as e:
            print("WORKER_ERROR:", repr(e))
            try:
                refund_credit(tg_user_id, 1)
            except Exception:
                pass
            update_job(job_id, {"status": "failed", "error": str(e), "finished_at": now_iso()})
            try:
                await bot.send_message(tg_user_id, f"❌ Проиозошла ошибка генерации. 1 кредит вернулся на ваш баланс ✅\n{e}", reply_markup=kb_result("reels"))
            except Exception:
                pass

        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("WORKER_FATAL_ERROR:\n" + traceback.format_exc(), flush=True)
        while True:
            time.sleep(60)
