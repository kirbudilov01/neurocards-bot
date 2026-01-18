import os

def req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

# Telegram
BOT_TOKEN = req("BOT_TOKEN")

# Database configuration
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "supabase").lower()  # supabase или postgres
DATABASE_URL = os.getenv("DATABASE_URL", "")  # для прямого PostgreSQL

# Supabase (для обратной совместимости)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET_INPUTS = os.getenv("SUPABASE_BUCKET_INPUTS", "inputs")
SUPABASE_BUCKET_OUTPUTS = os.getenv("SUPABASE_BUCKET_OUTPUTS", "outputs")

# OpenAI (для реальной генерации нейрокарточки сразу)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

# Kie AI (ключ уже добавил — ок; endpoint может добавишь позже)
KIE_API_KEY = os.getenv("KIE_API_KEY", "")
KIE_GENERATE_URL = os.getenv("KIE_GENERATE_URL", "")  # например: https://.../generate
