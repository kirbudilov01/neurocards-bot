from __future__ import annotations
import mimetypes
from typing import Optional
from app.db import supabase
from app.config import SUPABASE_BUCKET_INPUTS, SUPABASE_BUCKET_OUTPUTS

def upload_bytes(bucket: str, path: str, data: bytes, content_type: Optional[str] = None) -> str:
    if not content_type:
        content_type, _ = mimetypes.guess_type(path)
    file_options = {"content-type": content_type or "application/octet-stream"}

    supabase.storage.from_(bucket).upload(path, data, file_options=file_options)
    return path

def get_public_url(bucket: str, path: str) -> str:
    # если bucket public — будет нормальная ссылка
    return supabase.storage.from_(bucket).get_public_url(path)

def upload_input_photo(path: str, data: bytes) -> str:
    return upload_bytes(SUPABASE_BUCKET_INPUTS, path, data, content_type="image/jpeg")

def upload_output_file(path: str, data: bytes, content_type: str) -> str:
    return upload_bytes(SUPABASE_BUCKET_OUTPUTS, path, data, content_type=content_type)
