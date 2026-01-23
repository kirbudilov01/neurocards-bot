#!/usr/bin/env python3
"""
Полная проверка системы БЕЗ траты токенов KIE.AI
Проверяет все критические компоненты перед реальным тестом
"""
import asyncio
import os
import sys

# Добавляем путь к приложению
sys.path.insert(0, '/app')

async def test_gpt_with_proxy():
    """Тест 1: OpenAI GPT через прокси"""
    print("\n🧪 ТЕСТ 1: OpenAI GPT через прокси")
    print("=" * 60)
    
    try:
        from worker.openai_prompter import build_prompt_with_gpt
        from app.proxy_rotator import init_proxy_rotator
        from app.config import PROXY_FILE, load_proxies_from_file
        
        # Загружаем прокси из файла
        proxies = load_proxies_from_file(PROXY_FILE)
        if not proxies:
            print("❌ Не удалось загрузить прокси из файла")
            return False
        
        print(f"✅ Загружено {len(proxies)} прокси")
        
        # Инициализируем ProxyRotator
        init_proxy_rotator(proxies)
        print("✅ ProxyRotator инициализирован")
        
        # Пробуем запрос к GPT
        system = "You are a video prompt expert."
        instructions = "Create a short commercial video prompt."
        product_text = "TEST PRODUCT - red shoes"
        
        print("📤 Отправляем тестовый запрос к OpenAI GPT...")
        result = build_prompt_with_gpt(system, instructions, product_text, None)
        
        print(f"✅ GPT ОТВЕТИЛ: {result[:100]}...")
        return True
        
    except Exception as e:
        print(f"❌ GPT ОШИБКА: {e}")
        print(f"   Тип ошибки: {type(e).__name__}")
        if "403" in str(e):
            print("   ⚠️ OpenAI API блокирует запрос (прокси не работает)")
        elif "Unknown scheme" in str(e):
            print("   ⚠️ Неправильный формат прокси URL")
        return False


async def test_redis_connection():
    """Тест 2: Redis connection с увеличенным timeout"""
    print("\n🧪 ТЕСТ 2: Redis connection timeout")
    print("=" * 60)
    
    try:
        from app.services.redis_queue import get_redis_connection
        
        redis_conn = get_redis_connection()
        
        # Проверяем настройки соединения
        conn_kwargs = redis_conn.connection_pool.connection_kwargs
        socket_timeout = conn_kwargs.get('socket_timeout', 'НЕ ЗАДАН')
        socket_keepalive = conn_kwargs.get('socket_keepalive', 'НЕ ЗАДАН')
        health_check_interval = conn_kwargs.get('health_check_interval', 'НЕ ЗАДАН')
        
        print(f"📊 Redis connection settings:")
        print(f"   socket_timeout: {socket_timeout}")
        print(f"   socket_keepalive: {socket_keepalive}")
        print(f"   health_check_interval: {health_check_interval}")
        
        # Проверяем работу
        redis_conn.ping()
        print("✅ Redis PING успешен")
        
        if socket_timeout == 1800:
            print("✅ socket_timeout = 1800 (правильно)")
            return True
        else:
            print(f"⚠️ socket_timeout = {socket_timeout} (должно быть 1800)")
            return False
            
    except Exception as e:
        print(f"❌ Redis ОШИБКА: {e}")
        return False


async def test_queue_timeout():
    """Тест 3: Queue default_timeout"""
    print("\n🧪 ТЕСТ 3: Queue default_timeout")
    print("=" * 60)
    
    try:
        from app.services.redis_queue import get_queue
        
        queue = get_queue("neurocards")
        
        # В RQ Queue default_timeout хранится в объекте
        default_timeout = getattr(queue, 'default_timeout', None)
        
        print(f"📊 Queue default_timeout: {default_timeout}")
        
        if default_timeout == 1800:
            print("✅ default_timeout = 1800 (правильно)")
            return True
        else:
            print(f"⚠️ default_timeout = {default_timeout} (должно быть 1800)")
            return False
            
    except Exception as e:
        print(f"❌ Queue ОШИБКА: {e}")
        return False


async def test_proxy_rotator():
    """Тест 4: ProxyRotator загрузка и работа"""
    print("\n🧪 ТЕСТ 4: ProxyRotator")
    print("=" * 60)
    
    try:
        from app.proxy_rotator import init_proxy_rotator, get_proxy_rotator
        from app.config import PROXY_FILE, load_proxies_from_file
        
        proxies = load_proxies_from_file(PROXY_FILE)
        if not proxies:
            print("❌ Не удалось загрузить прокси из файла")
            return False
        
        init_proxy_rotator(proxies)
        rotator = get_proxy_rotator()
        
        if not rotator:
            print("❌ ProxyRotator НЕ инициализирован")
            return False
        
        proxy_count = len(rotator.proxies)
        print(f"📊 Загружено прокси: {proxy_count}")
        
        # Получаем несколько прокси
        proxy1 = rotator.get_next_proxy()
        proxy2 = rotator.get_next_proxy()
        proxy3 = rotator.get_next_proxy()
        
        print(f"✅ Прокси 1: {proxy1[:30]}...")
        print(f"✅ Прокси 2: {proxy2[:30]}...")
        print(f"✅ Прокси 3: {proxy3[:30]}...")
        
        # Проверяем формат
        if proxy1.startswith("http://"):
            print("✅ Формат прокси правильный (http://...)")
            return True
        else:
            print(f"⚠️ Неправильный формат прокси: {proxy1}")
            return False
            
    except Exception as e:
        print(f"❌ ProxyRotator ОШИБКА: {e}")
        return False


async def test_database_connection():
    """Тест 5: PostgreSQL connection pool"""
    print("\n🧪 ТЕСТ 5: PostgreSQL connection")
    print("=" * 60)
    
    try:
        from app.db_adapter import get_pool
        
        pool = await get_pool()
        
        if pool:
            print(f"✅ PostgreSQL pool создан")
            print(f"📊 Pool size: {pool.get_size()}")
            print(f"📊 Free connections: {pool.get_size() - pool.get_idle_size()}")
            
            # Пробуем запрос
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT COUNT(*) FROM users")
                print(f"✅ Пользователей в базе: {result}")
            
            return True
        else:
            print("❌ Pool не создан")
            return False
            
    except Exception as e:
        print(f"❌ PostgreSQL ОШИБКА: {e}")
        return False


async def test_storage():
    """Тест 6: Storage и nginx доступность"""
    print("\n🧪 ТЕСТ 6: Storage и nginx")
    print("=" * 60)
    
    try:
        from app.services.storage_factory import get_storage
        import httpx
        
        storage = await get_storage()
        print(f"✅ Storage инициализирован: {type(storage).__name__}")
        
        # Проверяем PUBLIC_BASE_URL
        from app.config import PUBLIC_BASE_URL
        print(f"📊 PUBLIC_BASE_URL: {PUBLIC_BASE_URL}")
        
        # Пробуем доступ к nginx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(PUBLIC_BASE_URL)
                print(f"✅ Nginx доступен, status: {response.status_code}")
                return True
        except Exception as e:
            print(f"⚠️ Nginx не отвечает: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Storage ОШИБКА: {e}")
        return False


async def main():
    """Запуск всех тестов"""
    print("\n" + "=" * 60)
    print("🚀 ПОЛНАЯ ПРОВЕРКА СИСТЕМЫ")
    print("=" * 60)
    
    results = {
        "GPT с прокси": await test_gpt_with_proxy(),
        "Redis connection": await test_redis_connection(),
        "Queue timeout": await test_queue_timeout(),
        "ProxyRotator": await test_proxy_rotator(),
        "PostgreSQL": await test_database_connection(),
        "Storage/nginx": await test_storage(),
    }
    
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТОВ")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("✅ Система готова к реальному тесту с KIE.AI")
        return 0
    else:
        print("❌ ЕСТЬ ПРОБЛЕМЫ!")
        print("⚠️ НЕ запускайте реальный тест - будут потрачены токены!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
