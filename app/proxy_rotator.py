"""
Proxy Rotator - централизованная система ротации прокси для всех сервисов
Использует round-robin и блокировку проблемных прокси
"""
import threading
import time
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class ProxyRotator:
    """
    Ротатор прокси для защиты от блокировок и распределения нагрузки.
    
    Features:
    - Round-robin распределение
    - Блокировка проблемных прокси на cooldown период
    - Thread-safe операции
    - Автоматическое восстановление заблокированных прокси
    """
    
    def __init__(self, proxies: List[str], cooldown_seconds: int = 300):
        """
        Args:
            proxies: Список прокси в формате "ip:port:user:pass"
            cooldown_seconds: Время блокировки прокси после ошибки (default 5 минут)
        """
        if not proxies:
            raise ValueError("Proxies list cannot be empty")
        
        self.proxies = proxies
        self.cooldown_seconds = cooldown_seconds
        
        # Состояние прокси
        self.current_index = 0
        self.blocked_proxies: Dict[str, float] = {}  # proxy -> timestamp когда разблокировать
        
        # Thread safety
        self.lock = threading.Lock()
        
        logger.info(f"🔄 ProxyRotator initialized with {len(proxies)} proxies")
    
    def get_next_proxy(self) -> Optional[str]:
        """
        Получить следующий доступный прокси (round-robin).
        Пропускает заблокированные прокси.
        
        Returns:
            Прокси в формате "ip:port:user:pass" или None если все заблокированы
        """
        with self.lock:
            # Очистить expired блокировки
            self._cleanup_expired_blocks()
            
            # Найти следующий незаблокированный прокси
            attempts = 0
            max_attempts = len(self.proxies)
            
            while attempts < max_attempts:
                proxy = self.proxies[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.proxies)
                attempts += 1
                
                if proxy not in self.blocked_proxies:
                    logger.debug(f"✅ Selected proxy: {self._mask_proxy(proxy)}")
                    return proxy
                else:
                    remaining = int(self.blocked_proxies[proxy] - time.time())
                    logger.debug(f"⏭️ Skipping blocked proxy {self._mask_proxy(proxy)} (unblock in {remaining}s)")
            
            logger.error("❌ All proxies are blocked!")
            return None
    
    def mark_as_failed(self, proxy: str, reason: str = ""):
        """
        Пометить прокси как проблемный и заблокировать на cooldown период.
        
        Args:
            proxy: Прокси который вызвал ошибку
            reason: Причина блокировки (для логирования)
        """
        with self.lock:
            unblock_time = time.time() + self.cooldown_seconds
            self.blocked_proxies[proxy] = unblock_time
            
            masked = self._mask_proxy(proxy)
            logger.warning(
                f"🚫 Proxy {masked} blocked for {self.cooldown_seconds}s. "
                f"Reason: {reason or 'unknown'}"
            )
    
    def mark_as_success(self, proxy: str):
        """
        Отметить успешное использование прокси (опционально, для статистики).
        
        Args:
            proxy: Прокси который успешно отработал
        """
        # В будущем можно добавить статистику success rate
        logger.debug(f"✅ Proxy {self._mask_proxy(proxy)} succeeded")
    
    def get_available_count(self) -> int:
        """
        Получить количество доступных (незаблокированных) прокси.
        
        Returns:
            Количество доступных прокси
        """
        with self.lock:
            self._cleanup_expired_blocks()
            return len(self.proxies) - len(self.blocked_proxies)
    
    def get_status(self) -> dict:
        """
        Получить текущий статус ротатора.
        
        Returns:
            Dict с информацией о прокси
        """
        with self.lock:
            self._cleanup_expired_blocks()
            return {
                "total": len(self.proxies),
                "available": len(self.proxies) - len(self.blocked_proxies),
                "blocked": len(self.blocked_proxies),
                "blocked_list": [
                    {
                        "proxy": self._mask_proxy(proxy),
                        "unblock_in": int(unblock_time - time.time())
                    }
                    for proxy, unblock_time in self.blocked_proxies.items()
                ]
            }
    
    def _cleanup_expired_blocks(self):
        """Удалить прокси у которых истек cooldown период."""
        current_time = time.time()
        expired = [
            proxy for proxy, unblock_time in self.blocked_proxies.items()
            if unblock_time <= current_time
        ]
        
        for proxy in expired:
            del self.blocked_proxies[proxy]
            logger.info(f"✅ Proxy {self._mask_proxy(proxy)} unblocked")
    
    @staticmethod
    def _mask_proxy(proxy: str) -> str:
        """Замаскировать чувствительные данные в прокси для логов."""
        parts = proxy.split(":")
        if len(parts) >= 4:
            # ip:port:user:pass -> ip:port:u***:p***
            return f"{parts[0]}:{parts[1]}:{parts[2][:1]}***:{parts[3][:1]}***"
        return proxy
    
    @staticmethod
    def format_for_aiohttp(proxy: str) -> str:
        """
        Конвертировать прокси в формат для aiohttp/aiogram.
        
        Args:
            proxy: "ip:port:user:pass"
        
        Returns:
            "http://user:pass@ip:port" для aiohttp
        """
        parts = proxy.split(":")
        if len(parts) == 4:
            ip, port, user, password = parts
            return f"http://{user}:{password}@{ip}:{port}"
        return proxy


# Глобальный инстанс (инициализируется в config.py)
_proxy_rotator: Optional[ProxyRotator] = None


def init_proxy_rotator(proxies: List[str], cooldown_seconds: int = 300):
    """
    Инициализировать глобальный ротатор прокси.
    Конвертирует прокси в формат http://user:pass@ip:port сразу при инициализации.
    """
    global _proxy_rotator
    # Форматируем все прокси сразу
    formatted_proxies = []
    for proxy in proxies:
        parts = proxy.split(":")
        if len(parts) == 4:
            ip, port, user, password = parts
            formatted = f"http://{user}:{password}@{ip}:{port}"
            formatted_proxies.append(formatted)
        else:
            logger.warning(f"⚠️ Invalid proxy format: {proxy}")
    
    if not formatted_proxies:
        logger.error("❌ No valid proxies found after formatting!")
        return
    
    _proxy_rotator = ProxyRotator(formatted_proxies, cooldown_seconds)
    logger.info(f"✅ Global ProxyRotator initialized with {len(formatted_proxies)} proxies")


def get_proxy_rotator() -> Optional[ProxyRotator]:
    """Получить глобальный ротатор прокси."""
    return _proxy_rotator
