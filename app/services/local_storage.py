"""
Локальное файловое хранилище (альтернатива Supabase Storage)
"""
import os
import aiofiles
from pathlib import Path
from typing import Optional, BinaryIO
import logging

logger = logging.getLogger(__name__)


class LocalStorage:
    """Локальное хранилище файлов на диске сервера"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.inputs_path = self.base_path / "inputs"
        self.outputs_path = self.base_path / "outputs"
        
        # Создаем директории если их нет
        self.inputs_path.mkdir(parents=True, exist_ok=True)
        self.outputs_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✅ LocalStorage initialized: {self.base_path}")
    
    async def upload_file(self, bucket: str, filename: str, file_data: bytes) -> str:
        """
        Загружает файл на диск
        
        Args:
            bucket: имя bucket'а (inputs/outputs)
            filename: имя файла
            file_data: содержимое файла в байтах
        
        Returns:
            Относительный путь к файлу
        """
        bucket_path = self.base_path / bucket
        bucket_path.mkdir(parents=True, exist_ok=True)
        
        file_path = bucket_path / filename
        
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_data)
            
            logger.info(f"✅ File uploaded: {bucket}/{filename}")
            return f"/{bucket}/{filename}"
            
        except Exception as e:
            logger.error(f"❌ Failed to upload file {bucket}/{filename}: {e}")
            raise
    
    async def upload_file_from_path(self, bucket: str, filename: str, local_file_path: str) -> str:
        """
        Загружает файл из локального пути
        
        Args:
            bucket: имя bucket'а (inputs/outputs)
            filename: имя файла для сохранения
            local_file_path: путь к исходному файлу
        
        Returns:
            Относительный путь к файлу
        """
        try:
            async with aiofiles.open(local_file_path, 'rb') as f:
                file_data = await f.read()
            
            return await self.upload_file(bucket, filename, file_data)
            
        except Exception as e:
            logger.error(f"❌ Failed to upload file from path {local_file_path}: {e}")
            raise
    
    async def get_public_url(self, bucket: str, filename: str) -> str:
        """
        Возвращает публичный URL для доступа к файлу
        
        Args:
            bucket: имя bucket'а
            filename: имя файла
        
        Returns:
            Полный URL для доступа к файлу
        """
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        return f"{base_url}/{bucket}/{filename}"
    
    async def download_file(self, bucket: str, filename: str) -> bytes:
        """
        Скачивает файл с диска
        
        Args:
            bucket: имя bucket'а
            filename: имя файла
        
        Returns:
            Содержимое файла в байтах
        """
        file_path = self.base_path / bucket / filename
        
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                data = await f.read()
            
            logger.info(f"✅ File downloaded: {bucket}/{filename}")
            return data
            
        except FileNotFoundError:
            logger.error(f"❌ File not found: {bucket}/{filename}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to download file {bucket}/{filename}: {e}")
            raise
    
    async def download_file_to_path(self, bucket: str, filename: str, local_file_path: str) -> None:
        """
        Скачивает файл и сохраняет по указанному пути
        
        Args:
            bucket: имя bucket'а
            filename: имя файла
            local_file_path: путь для сохранения
        """
        try:
            data = await self.download_file(bucket, filename)
            
            async with aiofiles.open(local_file_path, 'wb') as f:
                await f.write(data)
            
            logger.info(f"✅ File saved to: {local_file_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save file to {local_file_path}: {e}")
            raise
    
    def file_exists(self, bucket: str, filename: str) -> bool:
        """Проверяет существование файла"""
        file_path = self.base_path / bucket / filename
        return file_path.exists()
    
    async def delete_file(self, bucket: str, filename: str) -> None:
        """Удаляет файл"""
        file_path = self.base_path / bucket / filename
        
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"✅ File deleted: {bucket}/{filename}")
            else:
                logger.warning(f"⚠️ File not found for deletion: {bucket}/{filename}")
        except Exception as e:
            logger.error(f"❌ Failed to delete file {bucket}/{filename}: {e}")
            raise
    
    async def list_files(self, bucket: str, prefix: str = "") -> list[str]:
        """
        Возвращает список файлов в bucket'е
        
        Args:
            bucket: имя bucket'а
            prefix: префикс для фильтрации файлов
        
        Returns:
            Список имен файлов
        """
        bucket_path = self.base_path / bucket
        
        if not bucket_path.exists():
            return []
        
        files = []
        for file_path in bucket_path.glob(f"{prefix}*"):
            if file_path.is_file():
                files.append(file_path.name)
        
        return sorted(files)


# Глобальный инстанс для импорта
storage: Optional[LocalStorage] = None


def init_storage(base_path: str) -> LocalStorage:
    """Инициализирует глобальный инстанс хранилища"""
    global storage
    storage = LocalStorage(base_path)
    return storage
