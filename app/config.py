from dotenv import load_dotenv; import os; load_dotenv()
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Database configuration
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "postgres").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Redis Queue
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Storage
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
STORAGE_BASE_PATH = os.getenv("STORAGE_BASE_PATH", "/app/storage")

# Supabase (для обратной совместимости, если нужно)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET_INPUTS = os.getenv("SUPABASE_BUCKET_INPUTS", "inputs")
SUPABASE_BUCKET_OUTPUTS = os.getenv("SUPABASE_BUCKET_OUTPUTS", "outputs")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")
