"""
KIE API Key Rotator
Управляет пулом API ключей для KIE.AI с балансировкой нагрузки и обработкой rate limits
"""
import os
import time
import logging
from typing import List, Optional, Dict
from threading import Lock

logger = logging.getLogger(__name__)


class KieKeyRotator:
    """Ротатор API ключей для KIE.AI с round-robin и health tracking"""
    
    def __init__(self):
        self._keys = self._load_keys()
        self._current_index = 0
        self._lock = Lock()
        self._health: Dict[str, Dict] = {}  # key -> {failures: int, blocked_until: float}
        
        logger.info(f"✅ KieKeyRotator initialized with {len(self._keys)} keys")
    
    def _load_keys(self) -> List[str]:
        """Загружает API ключи из переменных окружения"""
        keys = []
        
        # Поддержка одного или нескольких ключей через запятую
        keys_str = os.getenv("KIE_API_KEY", "").strip()
        if keys_str:
            # Разделяем по запятой и очищаем
            keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        
        # Поддержка пула ключей (KIE_API_KEY_1, KIE_API_KEY_2, ...) - для обратной совместимости
        i = 1
        while True:
            key = os.getenv(f"KIE_API_KEY_{i}", "").strip()
            if not key:
                break
            if key not in keys:  # Избегаем дублей
                keys.append(key)
            i += 1
        
        if not keys:
            raise RuntimeError("No KIE API keys found. Set KIE_API_KEY (comma-separated) or KIE_API_KEY_1, KIE_API_KEY_2, ...")
        
        logger.info(f"📋 Loaded {len(keys)} KIE API key(s)")
        return keys
    
    def get_key(self) -> str:
        """Возвращает следующий доступный API ключ (round-robin)"""
        with self._lock:
            now = time.time()
            
            # Пробуем найти здоровый ключ
            for _ in range(len(self._keys)):
                key = self._keys[self._current_index]
                self._current_index = (self._current_index + 1) % len(self._keys)
                
                # Проверяем здоровье ключа
                health = self._health.get(key, {})
                blocked_until = health.get("blocked_until", 0)
                
                if now >= blocked_until:
                    return key
            
            # Если все ключи заблокированы - возвращаем первый (пусть пробует)
            logger.warning("⚠️ All KIE API keys are blocked, using first one anyway")
            return self._keys[0]
    
    def mark_failed(self, key: Optional[str]):
        """Универсальный метод для пометки неудачного использования ключа"""
        if not key:
            return
        
        with self._lock:
            if key not in self._health:
                self._health[key] = {"failures": 0, "blocked_until": 0}
            
            self._health[key]["failures"] += 1
            
            # Блокируем на короткое время (1 минута) после неудачи
            self._health[key]["blocked_until"] = time.time() + 60
            
            logger.warning(f"⚠️ KIE API key marked as failed, blocked for 1 minute")
    
    def report_success(self, key: str):
        """Отмечает успешное использование ключа"""
        with self._lock:
            if key in self._health:
                self._health[key]["failures"] = 0
    
    def report_rate_limit(self, key: str, cooldown_minutes: int = 60):
        """Отмечает rate limit для ключа и блокирует его на время"""
        with self._lock:
            if key not in self._health:
                self._health[key] = {"failures": 0, "blocked_until": 0}
            
            self._health[key]["failures"] += 1
            self._health[key]["blocked_until"] = time.time() + (cooldown_minutes * 60)
            
            logger.warning(
                f"⚠️ KIE API key rate limited (failures: {self._health[key]['failures']}), "
                f"blocked for {cooldown_minutes} minutes"
            )
    
    def report_billing_error(self, key: str):
        """Отмечает проблему с биллингом и блокирует ключ на долгое время"""
        with self._lock:
            if key not in self._health:
                self._health[key] = {"failures": 0, "blocked_until": 0}
            
            self._health[key]["failures"] += 1
            self._health[key]["blocked_until"] = time.time() + (24 * 3600)  # 24 часа
            
            logger.error(
                f"❌ KIE API key billing error, blocked for 24 hours. "
                f"Check your KIE account!"
            )
    
    def get_stats(self) -> Dict:
        """Возвращает статистику по ключам"""
        with self._lock:
            now = time.time()
            healthy = sum(1 for key in self._keys 
                         if self._health.get(key, {}).get("blocked_until", 0) <= now)
            
            return {
                "total_keys": len(self._keys),
                "healthy_keys": healthy,
                "blocked_keys": len(self._keys) - healthy,
                "health": {
                    i: {
                        "blocked": self._health.get(key, {}).get("blocked_until", 0) > now,
                        "failures": self._health.get(key, {}).get("failures", 0)
                    }
                    for i, key in enumerate(self._keys, 1)
                }
            }


# Глобальный инстанс ротатора
_rotator: Optional[KieKeyRotator] = None


def get_rotator() -> KieKeyRotator:
    """Возвращает глобальный инстанс ротатора (singleton)"""
    global _rotator
    if _rotator is None:
        _rotator = KieKeyRotator()
    return _rotator
