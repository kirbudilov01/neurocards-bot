"""
Utility functions
"""
import json
from typing import Any


def ensure_dict(value: Any) -> dict:
    """
    Гарантирует что значение будет dict
    Если строка - парсит JSON
    Если dict - возвращает как есть
    Иначе - оборачивает в {"text": str(value)}
    """
    if isinstance(value, dict):
        return value
    
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return {"text": value}
    
    return {"text": str(value)}


def ensure_json_string(value: Any) -> str:
    """
    Гарантирует что значение будет JSON string
    Если dict - сериализует в JSON
    Если уже string - проверяет валидность и возвращает
    """
    if isinstance(value, dict):
        return json.dumps(value)
    
    if isinstance(value, str):
        try:
            # Проверяем что это валидный JSON
            json.loads(value)
            return value
        except (json.JSONDecodeError, ValueError):
            # Если не JSON - оборачиваем в dict
            return json.dumps({"text": value})
    
    return json.dumps({"text": str(value)})
