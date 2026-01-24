"""
KIE API Error Classifier
Классифицирует ошибки от KIE.AI для правильной обработки и retry логики
"""
import re
from enum import Enum
from typing import Optional, Dict, Any


class KieErrorType(Enum):
    """Типы ошибок от KIE API"""
    USER_VIOLATION = "user_violation"  # Нарушение правил (плохое фото/промпт)
    BILLING = "billing"  # Проблемы с биллингом/аккаунтом
    RATE_LIMIT = "rate_limit"  # Превышен rate limit
    TEMPORARY = "temporary"  # Временная ошибка (503, timeout)
    UNKNOWN = "unknown"  # Неизвестная ошибка


def classify_kie_error(info: Dict[str, Any]) -> tuple[KieErrorType, str]:
    """
    Классифицирует ответ от KIE API на тип ошибки
    
    Args:
        info: Ответ от poll_record_info
        
    Returns:
        (error_type, error_message)
    """
    # Извлекаем сообщение об ошибке
    error_msg = _extract_error_message(info)
    if not error_msg:
        return (KieErrorType.UNKNOWN, "No error message found")
    
    error_lower = error_msg.lower()
    
    # 1. Policy/Content Violations (USER_VIOLATION)
    policy_keywords = [
        "policy", "content", "inappropriate", "violation", "rule", "guideline",
        "safety", "prohibited", "restricted", "denied", "rejected", "banned",
        "nsfw", "explicit", "harmful", "offensive", "abuse", "illegal",
        "copyright", "trademark", "privacy", "terms of service", "tos"
    ]
    if any(keyword in error_lower for keyword in policy_keywords):
        return (KieErrorType.USER_VIOLATION, error_msg)
    
    # 2. Billing/Account Issues (BILLING)
    billing_keywords = [
        "billing", "payment", "subscription", "credit", "balance", "quota exceeded",
        "account", "insufficient funds", "expired", "suspended", "disabled",
        "payment method", "plan limit", "upgrade", "purchase"
    ]
    if any(keyword in error_lower for keyword in billing_keywords):
        return (KieErrorType.BILLING, error_msg)
    
    # 3. Rate Limiting (RATE_LIMIT)
    rate_limit_keywords = [
        "rate limit", "too many requests", "throttle", "429", "slow down",
        "max requests", "requests per", "concurrent limit"
    ]
    if any(keyword in error_lower for keyword in rate_limit_keywords):
        return (KieErrorType.RATE_LIMIT, error_msg)
    
    # 4. Temporary Errors (TEMPORARY)
    temporary_keywords = [
        "timeout", "503", "502", "500", "service unavailable", "temporary",
        "try again", "retry", "network", "connection", "server error",
        "maintenance", "overloaded", "busy", "internal error"
    ]
    if any(keyword in error_lower for keyword in temporary_keywords):
        return (KieErrorType.TEMPORARY, error_msg)
    
    # 5. Unknown
    return (KieErrorType.UNKNOWN, error_msg)


def _extract_error_message(info: Dict[str, Any]) -> Optional[str]:
    """Извлекает сообщение об ошибке из ответа KIE"""
    if not isinstance(info, dict):
        return None
    
    # Проверяем разные возможные поля с ошибкой
    error_fields = [
        "error", "error_message", "errorMessage", "message", "msg",
        "failMsg", "fail_msg", "reason", "detail", "details"
    ]
    
    # Ищем в корне
    for field in error_fields:
        if field in info and info[field]:
            return str(info[field])
    
    # Ищем в data
    data = info.get("data")
    if isinstance(data, dict):
        for field in error_fields:
            if field in data and data[field]:
                return str(data[field])
        
        # Проверяем state/status
        state = data.get("state") or data.get("status") or ""
        if isinstance(state, str) and state.lower() in {"fail", "failed", "error"}:
            # Ищем сообщение об ошибке
            for field in error_fields:
                if field in data and data[field]:
                    return str(data[field])
    
    return None


def should_retry(error_type: KieErrorType, attempt: int, max_attempts: int = 3) -> bool:
    """
    Определяет, нужно ли делать retry
    
    Args:
        error_type: Тип ошибки
        attempt: Текущая попытка (начиная с 1)
        max_attempts: Максимальное количество попыток
        
    Returns:
        True если нужен retry, False если нет
    """
    if attempt >= max_attempts:
        return False
    
    # Retry только для временных ошибок и rate limit
    return error_type in {KieErrorType.TEMPORARY, KieErrorType.RATE_LIMIT}


def get_retry_delay(error_type: KieErrorType, attempt: int) -> int:
    """
    Возвращает задержку перед retry (в секундах)
    Использует exponential backoff
    
    Args:
        error_type: Тип ошибки
        attempt: Номер попытки (начиная с 1)
        
    Returns:
        Задержка в секундах
    """
    if error_type == KieErrorType.RATE_LIMIT:
        # Для rate limit - большая задержка
        return min(60 * (2 ** attempt), 600)  # max 10 минут
    
    if error_type == KieErrorType.TEMPORARY:
        # Для временных - exponential backoff
        return min(10 * (2 ** attempt), 120)  # max 2 минуты
    
    return 0


def get_user_error_message(error_type: KieErrorType) -> str:
    """Возвращает сообщение для пользователя в зависимости от типа ошибки"""
    if error_type == KieErrorType.USER_VIOLATION:
        return (
            "⚠️ <b>Вы нарушили правила SORA 2</b>\n\n"
            "Внимательно изучите требования к:\n"
            "• фото (чаще всего проблема в фото)\n"
            "• промпту\n\n"
            "💰 1 кредит вернули на баланс ✅"
        )
    
    if error_type == KieErrorType.BILLING:
        return (
            "⚠️ <b>Временные технические неполадки</b>\n\n"
            "🛠️ Обратитесь в службу поддержки: @fabricbothelper\n\n"
            "💰 1 кредит вернули на баланс ✅"
        )
    
    if error_type == KieErrorType.RATE_LIMIT:
        return (
            "⏳ <b>Сервис временно перегружен</b>\n\n"
            "Попробуйте через несколько минут.\n\n"
            "💰 1 кредит вернули на баланс ✅"
        )
    
    if error_type == KieErrorType.TEMPORARY:
        return (
            "⚠️ <b>Временная ошибка генерации</b>\n\n"
            "🔄 Мы попробуем ещё раз автоматически.\n"
            "Если не получится - вернём кредит."
        )
    
    # UNKNOWN
    return (
        "❌ <b>Произошла ошибка генерации</b>\n\n"
        "🛠️ Обратитесь в службу поддержки: @fabricbothelper\n\n"
        "💰 1 кредит вернули на баланс ✅"
    )
