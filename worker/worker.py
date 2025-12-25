import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import importlib.util

from aiogram import Bot
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent  # .../worker


def load_module(module_name: str, file_name: str):
    file_path = BASE_DIR / file_name
    if not file_path.exists():
        raise RuntimeError(f"Missing file: {file_path}")

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module spec: {module_name} from {file_path}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kie = load_module("kie_client", "kie_client.py")
prompter = load_module("openai_prompter", "openai_prompter.py")
templates = load_module("prompt_templates", "prompt_templates.py")

create_task_sora_i2v = getattr(kie, "create_task_sora_i2v")
poll_record_info = getattr(kie, "poll_record_info")
build_prompt_with_gpt = getattr(prompter, "build_prompt_with_gpt")

# Шаблон: сначала новый, потом fallback на старый
REELS_TEMPLATE = getattr(templates, "REELS_UGC_TEMPLATE_V1", None) or getattr(templates, "REELS_TEMPLATE_1", None)
if not REELS_TEMPLATE:
    raise RuntimeError("Missing template in prompt_templates.py: REELS_UGC_TEMPLATE_V1 or REELS_TEMPLATE_1")


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
    pub = supabase.storage.from_("inputs").get_public_url(input_path)
    if isinstance(pub, dict):
        return pub.get("publicUrl") or pub.get("publicURL") or pub.get("public_url") or str(pub)
    return str(pub)


async def main():
    bot = Bot(BOT_TOKEN)
    print("Worker started (Kie v1 reels, resilient imports).")

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

            kind = job.get("kind")
            if kind != "reels":
                update_job(job_id, {"status": "failed", "error": "only_reels_supported_v1", "finished_at": now_iso()})
                await bot.send_message(tg_user_id, "Пока поддерживается только 🎬 REELS. Нейрокарточки подключим позже.")
                await asyncio.sleep(1)
                continue

            product_text = (job.get("product_info") or {}).get("text", "")
            extra_wishes = job.get("extra_wishes")

            input_path = job.get("input_photo_path")
            if not input_path:
                raise RuntimeError("job.input_photo_path is empty")

            input_url = get_public_input_url(input_path)

            tpl = REELS_TEMPLATE
            script_and_prompt = build_prompt_with_gpt(
                system=tpl["system"],
                instructions=tpl["instructions"],
                product_text=product_text,
                extra_wishes=extra_wishes,
            )

            task_id = create_task_sora_i2v(prompt=script_and_prompt, image_url=input_url)

            await bot.send_message(
                tg_user_id,
                "✅ Сценарий и промпт собраны и отправлены в генерацию.\n"
                "⏳ Ожидай 3–5 минут. Я пришлю результат."
            )

            info = poll_record_info(task_id)

            print("\n==== KIE recordInfo raw ====")
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("==== /KIE recordInfo raw ====\n")

            update_job(job_id, {"status": "done", "finished_at": now_iso(), "kie_task_id": task_id})

            await bot.send_message(
                tg_user_id,
                "🧩 Я получил ответ от Kie.\n"
                "Сейчас в логах воркера есть JSON — по нему в следующем шаге достанем ссылку на mp4."
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
