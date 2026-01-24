from dotenv import load_dotenv; import os; load_dotenv()
import os
import logging

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Database configuration
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "postgres").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Redis Queue
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Storage
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
STORAGE_BASE_PATH = os.getenv("STORAGE_BASE_PATH", "/app/storage")

# Supabase support removed - using PostgreSQL only

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")

# Support & UI
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/fabricbothelper")

# Welcome video file_id (after first upload to Telegram)
# If empty, will use FSInputFile to upload from disk (slow!)
WELCOME_VIDEO_FILE_ID = os.getenv("WELCOME_VIDEO_FILE_ID", "")

# Proxy Configuration
PROXY_FILE = os.getenv("PROXY_FILE", "/app/proxies.txt")
PROXY_COOLDOWN = int(os.getenv("PROXY_COOLDOWN", "300"))  # 5 минут по умолчанию

def load_proxies_from_file(filepath: str) -> list:
    """Загрузить прокси из файла (один прокси на строку в формате ip:port:user:pass)."""
    try:
        if not os.path.exists(filepath):
            logger.warning(f"⚠️ Proxy file not found: {filepath}")
            return []
        
        with open(filepath, 'r') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        logger.info(f"✅ Loaded {len(proxies)} proxies from {filepath}")
        return proxies
    except Exception as e:
        logger.error(f"❌ Failed to load proxies from {filepath}: {e}")
        return []
