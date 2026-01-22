"""
Storage Factory - автоматически выбирает тип хранилища
"""
import os
import logging

logger = logging.getLogger(__name__)

STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local").lower()
LOCAL_STORAGE_BASE_PATH = os.getenv("LOCAL_STORAGE_BASE_PATH", "/var/neurocards/storage")


def get_storage():
    """
    Возвращает объект хранилища в зависимости от STORAGE_TYPE
    """
    if STORAGE_TYPE == "local":
        logger.info(f"📁 Using LOCAL storage at {LOCAL_STORAGE_BASE_PATH}")
        from app.services.local_storage import LocalStorage
        return LocalStorage(base_path=LOCAL_STORAGE_BASE_PATH)
    else:
        logger.info("☁️ Using SUPABASE storage")
        from app.services import storage
        return storage


# Глобальный инстанс
_storage_instance = None


def get_storage_instance():
    """Singleton для хранилища"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = get_storage()
    return _storage_instance
