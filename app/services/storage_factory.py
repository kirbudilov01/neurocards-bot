"""
Фабрика для получения нужного типа хранилища (Supabase или локальное)
"""
import os
import logging
from typing import Union, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.storage import SupabaseStorage
    from app.services.local_storage import LocalStorage

logger = logging.getLogger(__name__)


def get_storage() -> Union['SupabaseStorage', 'LocalStorage']:
    """
    Возвращает инстанс хранилища в зависимости от конфигурации
    
    Определяется по переменной окружения STORAGE_TYPE:
    - "local" - локальное файловое хранилище
    - "supabase" (по умолчанию) - Supabase Storage
    """
    storage_type = os.getenv("STORAGE_TYPE", "supabase").lower()
    
    if storage_type == "local":
        logger.info("📁 Using LOCAL storage")
        from app.services.local_storage import storage, init_storage
        
        if storage is None:
            storage_path = os.getenv("STORAGE_PATH", "/var/neurocards/storage")
            logger.info(f"📁 Initializing local storage at: {storage_path}")
            return init_storage(storage_path)
        
        return storage
    
    else:
        logger.info("☁️ Using SUPABASE storage")
        from app.services.storage import storage
        return storage


# Экспортируем для удобного импорта
storage = get_storage()
