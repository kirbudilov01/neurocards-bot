from __future__ import annotations

import mimetypes
from typing import Optional, Union

from app.db import supabase
from app.config import SUPABASE_BUCKET_INPUTS, SUPABASE_BUCKET_OUTPUTS


def normalize_path(bucket: str, path: str) -> str:
    p = (path or "").strip().lstrip("/")
    prefix = f"{bucket}/"
    while p.startswith(prefix):
        p = p[len(prefix):]
    return p


def upload_bytes(bucket: str, path: str, data: bytes, content_type: Optional[str] = None) -> str:
    p = normalize_path(bucket, path)

    if not content_type:
        content_type, _ = mimetypes.guess_type(p)

    file_options = {"content-type": content_type or "application/octet-stream"}

    # ✅ максимально совместимо: file_options передаём позиционно
    supabase.storage.from_(bucket).upload(p, data, file_options)

    return p


def get_public_url(bucket: str, path: str) -> str:
    p = normalize_path(bucket, path)
    res: Union[str, dict] = supabase.storage.from_(bucket).get_public_url(p)

    if isinstance(res, dict):
        return res.get("publicUrl") or res.get("public_url") or str(res)

    return str(res)


def upload_input_photo(path: str, data: bytes) -> str:
    return upload_bytes(SUPABASE_BUCKET_INPUTS, path, data, content_type="image/jpeg")


def upload_output_file(path: str, data: bytes, content_type: str) -> str:
    return upload_bytes(SUPABASE_BUCKET_OUTPUTS, path, data, content_type=content_type)
