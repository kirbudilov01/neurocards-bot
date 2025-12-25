import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import importlib.util

print("WORKER_BOOT: reached worker.py top-level")

# ---------- безопасная загрузка модулей по файлам ----------
BASE_DIR = Path(__file__).resolve().parent  # /worker


def load_module(name: str, filename: str):
    path = BASE_DIR / filename
    if not path.exists():
        raise RuntimeError(f"Missing file: {path}")

    spec = importlib.util.spec_from_file_location(name, str(path))
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module: {filename}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kie = load_module("kie_client", "kie_client.py")
prompter = load_module("openai_prompter", "openai_prompter.py")
templates = load_module("prompt_templates", "prompt_templates.py")

create_task_sora_i2v = kie.create_task_sora_i2v
poll_record_info = kie.poll_record_info
build_prompt_with_gpt = prompter.build_prompt_with_gpt

# шаблон — сначала новый, потом fallback
REELS_TEMPLATE = (
    getattr(templates, "REELS_UGC_TEMPLATE_V1", None)
    or getattr(templates, "REELS_TEMPLATE_1", None)
)

if not REELS_TEMPLATE:
    raise RuntimeError("No REELS template found in prompt_templates.py")


# ---------- ENV ----------
def req(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val.strip()


BOT_TOKEN = req("BOT_TOKEN")
SUPABASE_URL = req("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = req("SUPABASE_SERVICE_ROLE_KEY")

from aiogram import Bot
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- DB ----------
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


def get_public_input_url(path: str) -> str:
    pub = supabase.storage.from_("inputs").get_public_url(path)
    if isinstance(pub, dict):
        return pub.get("publicUrl") or pub.get("public_url") or str(pub)
    return str(pub)


# ---------- MAIN ----------
async def main():
    print("WORKER_BOOT: entered main()")

    bot = Bot(BOT_TOKEN)

    while True:
        job = fetch_next_queued_job()
        if not job:
            await asyncio.sleep(2)
            continue

        job_id = job["id"]
        print("WORKER_JOB: picked job", job_id)

        user = get_user_by_id(job["user_id"])
        if not user:
            update_job(job_id, {"status": "failed", "error": "user_not_found"})
            continue

        tg_user_id = user["tg_user_id"]

        try:
            update_job(job_id, {"status": "processing", "started_at": now_iso()})

            if job.get("kind") != "reels":
                raise RuntimeError("Only reels supported")

            input_path = job.get("input_photo_path")
            if not input_path:
                raise RuntimeError("Missing input_photo_path")

            image_url = get_public_input_url(input_path)

            script = build_prompt_with_gpt(
                system=REELS_TEMPLATE["system"],
                instructions=REELS_TEMPLATE["instructions"],
                product_text=(job.get("product_info") or {}).get("text", ""),
                extra_wishes=job.get("extra_wishes"),
            )

            task_id = create_task_sora_i2v(
                prompt=script,
                image_url=image_url,
            )

            await bot.send_message(
                tg_user_id,
                "🎬 Генерация запущена. Ожидай 3–5 минут."
            )

            info = poll_record_info(task_id)

            print("KIE_RESULT:")
            print(json.dumps(info, indent=2, ensure_ascii=False))

            update_job(
                job_id,
                {
                    "status": "done",
                    "finished_at": now_iso(),
                    "kie_task_id": task_id,
                },
            )

            await bot.send_message(
                tg_user_id,
                "✅ Генерация завершена. Видео получено (пока в логах)."
            )

        except Exception as e:
            print("WORKER_ERROR:", repr(e))
            update_job(
                job_id,
                {
                    "status": "failed",
                    "error": str(e),
                    "finished_at": now_iso(),
                },
            )
            try:
                await bot.send_message(tg_user_id, f"❌ Ошибка генерации:\n{e}")
            except Exception:
                pass

        await asyncio.sleep(1)


# ---------- ENTRY ----------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("WORKER_FATAL:", repr(e))
        raise
