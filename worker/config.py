import os

def req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

# Telegram
BOT_TOKEN = req("BOT_TOKEN")

# Database configuration
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "postgres").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Redis Queue
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUES = ["neurocards"]

# Worker settings
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "5"))

# Storage
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
STORAGE_BASE_PATH = os.getenv("STORAGE_BASE_PATH", "/app/storage")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# KIE AI (можно несколько ключей через запятую)
KIE_API_KEY = os.getenv("KIE_API_KEY", "")
