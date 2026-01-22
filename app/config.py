from dotenv import load_dotenv; import os; load_dotenv()
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Database configuration
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "supabase").lower()  # supabase или postgres
DATABASE_URL = os.getenv("DATABASE_URL", "")  # для прямого PostgreSQL

# Supabase (для обратной совместимости)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

SUPABASE_BUCKET_INPUTS = os.getenv("SUPABASE_BUCKET_INPUTS", "inputs")
SUPABASE_BUCKET_OUTPUTS = os.getenv("SUPABASE_BUCKET_OUTPUTS", "outputs")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")  # опционально
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")
