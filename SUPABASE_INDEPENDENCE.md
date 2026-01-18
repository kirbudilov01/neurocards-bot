# ✅ ПОЛНАЯ НЕЗАВИСИМОСТЬ ОТ SUPABASE

## 🎯 Что сделано

### ✅ Bot (app/) - 100% готов
- Все handlers используют `db_adapter.py` вместо прямых Supabase вызовов
- Поддержка 2 режимов БД: PostgreSQL (asyncpg) и Supabase (SDK)
- Переключение через `DATABASE_TYPE` env var
- Connection pooling для PostgreSQL

### ✅ Worker (worker/) - 100% готов
- Полная миграция на `db_adapter.py`
- Использует `storage_factory` для файлов
- Поддержка локального и Supabase storage
- Graceful shutdown и retry логика

### ✅ Storage (app/services/)
- `local_storage.py` - локальное файловое хранилище
- `storage_factory.py` - автоматический выбор backend
- Переключение через `STORAGE_TYPE` env var

### ✅ Database (app/)
- `db_adapter.py` - универсальный адаптер БД
- Все функции: get_or_create_user, create_job_and_consume_credit, refund_credit, etc.
- Поддержка PostgreSQL RPC функций (stored procedures)

### ✅ Deployment
- `scripts/deploy_to_vps.sh` - полная автоматическая установка
- `scripts/update_vps.sh` - обновления
- `scripts/monitor_vps.sh` - мониторинг
- `scripts/backup_vps.sh` - бэкапы
- Systemd services для bot и worker
- Nginx для раздачи статических файлов

## 🏗️ Архитектура решения

```
┌─────────────────────────────────────────────────────────────┐
│                     NEUROCARDS BOT                           │
│                                                               │
│  ┌─────────────┐          ┌─────────────┐                   │
│  │   Telegram  │          │   Telegram  │                   │
│  │   Bot API   │          │   Bot API   │                   │
│  └──────┬──────┘          └──────┬──────┘                   │
│         │                         │                          │
│         │                         │                          │
│  ┌──────▼──────────────┐  ┌──────▼──────────────┐          │
│  │    BOT SERVICE      │  │   WORKER SERVICE    │          │
│  │   (app/main.py)     │  │  (worker/worker.py) │          │
│  │                     │  │                     │          │
│  │  • Webhook handler  │  │  • Job processor    │          │
│  │  • User commands    │  │  • Video generation │          │
│  │  • Job creation     │  │  • KIE.AI client    │          │
│  └──────┬──────────────┘  └──────┬──────────────┘          │
│         │                         │                          │
│         └────────┬────────────────┘                          │
│                  │                                           │
│         ┌────────▼─────────┐                                │
│         │   DB ADAPTER     │                                │
│         │ (db_adapter.py)  │                                │
│         │                  │                                │
│         │  • Universal API │                                │
│         │  • Dual mode     │                                │
│         └────────┬─────────┘                                │
│                  │                                           │
│        ┌─────────┴──────────┐                               │
│        │                    │                               │
│  ┌─────▼──────┐      ┌──────▼──────┐                       │
│  │ PostgreSQL │      │  Supabase   │                       │
│  │  (asyncpg) │      │    (SDK)    │                       │
│  │            │      │             │                       │
│  │ DATABASE_  │      │ DATABASE_   │                       │
│  │ TYPE=      │      │ TYPE=       │                       │
│  │ postgres   │      │ supabase    │                       │
│  └────────────┘      └─────────────┘                       │
│                                                               │
│         ┌────────────────────┐                              │
│         │  STORAGE FACTORY   │                              │
│         │ (storage_factory)  │                              │
│         └────────┬───────────┘                              │
│                  │                                           │
│        ┌─────────┴──────────┐                               │
│        │                    │                               │
│  ┌─────▼──────┐      ┌──────▼──────┐                       │
│  │   LOCAL    │      │  Supabase   │                       │
│  │ FILESYSTEM │      │   Storage   │                       │
│  │            │      │             │                       │
│  │ STORAGE_   │      │ STORAGE_    │                       │
│  │ TYPE=local │      │ TYPE=       │                       │
│  │            │      │ supabase    │                       │
│  └────────────┘      └─────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

## 🎨 Режимы работы

### Режим 1: Полная независимость (VPS)
```bash
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://botuser:password@localhost:5432/neurocards
STORAGE_TYPE=local
STORAGE_BASE_PATH=/var/neurocards/storage
PUBLIC_DOMAIN=https://yourdomain.com
```

**Преимущества:**
- ✅ Нет зависимости от внешних сервисов
- ✅ Полный контроль
- ✅ Экономия $20-25/месяц
- ✅ Быстрее (всё локально)

### Режим 2: Managed сервисы (Render + Supabase)
```bash
DATABASE_TYPE=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key
STORAGE_TYPE=supabase
```

**Преимущества:**
- ✅ Не нужно настраивать инфраструктуру
- ✅ Автоматические бэкапы
- ✅ Масштабирование из коробки

### Режим 3: Гибрид
```bash
# PostgreSQL локально, файлы в Supabase
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://...
STORAGE_TYPE=supabase
SUPABASE_URL=...
```

## 📁 Структура проекта

```
neurocards-bot/
├── app/
│   ├── config.py           # Конфигурация с поддержкой обоих режимов
│   ├── db_adapter.py       # ✅ Универсальный database adapter
│   ├── db.py               # DEPRECATED - старый Supabase-only код
│   ├── main.py             # Bot entry point с init_db_pool()
│   ├── handlers/           # Все используют db_adapter
│   │   ├── cabinet.py      
│   │   ├── flow_neurocard.py
│   │   ├── flow_reels.py
│   │   └── ...
│   └── services/
│       ├── storage_factory.py    # ✅ Выбор storage backend
│       ├── local_storage.py      # ✅ Локальное хранилище
│       ├── storage.py             # Supabase storage wrapper
│       └── generation.py          # Использует db_adapter
│
├── worker/
│   ├── config.py           # С поддержкой DATABASE_TYPE
│   └── worker.py           # ✅ Полностью мигрирован на db_adapter
│
├── scripts/
│   ├── deploy_to_vps.sh    # ✅ Автоматический деплой
│   ├── update_vps.sh       # ✅ Обновление бота
│   ├── monitor_vps.sh      # ✅ Мониторинг
│   └── backup_vps.sh       # ✅ Бэкапы
│
├── supabase/
│   ├── schema.sql          # Полная схема БД (работает с PostgreSQL)
│   └── rpc.sql             # RPC функции (stored procedures)
│
├── .env.example            # ✅ Обновлён с DATABASE_TYPE и STORAGE_TYPE
├── requirements.txt        # ✅ Добавлены asyncpg, aiofiles
├── README.md               # ✅ Обновлён с новой архитектурой
├── DATABASE_ADAPTER.md     # Документация по миграции
└── SELF_HOSTING.md         # Полная инструкция по VPS деплою
```

## 🔧 Ключевые изменения

### 1. Database Adapter (db_adapter.py)

**Было (app/db.py):**
```python
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_or_create_user(tg_user_id):
    res = supabase.table("users").select("*").eq("tg_user_id", tg_user_id).execute()
    if res.data:
        return res.data[0]
    # ...
```

**Стало (app/db_adapter.py):**
```python
import asyncpg
from app import config

_pool = None

async def init_db_pool():
    global _pool
    if config.DATABASE_TYPE == "postgres":
        _pool = await asyncpg.create_pool(config.DATABASE_URL)
    # для supabase используем SDK

async def get_or_create_user(tg_user_id: int):
    if config.DATABASE_TYPE == "postgres":
        async with _pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM users WHERE tg_user_id = $1",
                tg_user_id
            )
    else:
        # Supabase SDK
        res = supabase.table("users").select("*").eq("tg_user_id", tg_user_id).execute()
        return res.data[0] if res.data else None
```

### 2. Storage Factory

**Было:**
```python
from app.services.storage import SupabaseStorage

file_storage = SupabaseStorage(supabase)
```

**Стало:**
```python
from app.services.storage_factory import get_storage

storage = get_storage()  # автоматически выбирает backend
await storage.upload_file("inputs", "photo.jpg", data)
```

### 3. Worker Migration

**Было (worker/worker.py):**
```python
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_next_queued_job():
    res = supabase.table("jobs").select("*").eq("status", "queued").execute()
    return res.data[0] if res.data else None
```

**Стало:**
```python
from app.db_adapter import init_db_pool, fetch_next_queued_job

async def main():
    await init_db_pool()
    
    while not shutdown_flag:
        job = await fetch_next_queued_job()
        # ...
```

## 🚀 Как использовать

### Вариант 1: VPS Self-Hosting (рекомендуется)

1. **Купить VPS** (Hetzner, DigitalOcean, Vultr):
   - 2 vCPU
   - 4 GB RAM
   - 80 GB SSD
   - ~$5-10/месяц

2. **Деплой в один клик:**
   ```bash
   ./scripts/deploy_to_vps.sh YOUR_SERVER_IP
   ```

3. **Настроить .env на сервере:**
   ```bash
   ssh root@YOUR_SERVER_IP
   cd /var/neurocards
   nano .env
   ```
   
   Установить:
   ```bash
   DATABASE_TYPE=postgres
   DATABASE_URL=postgresql://neurocards:your_pass@localhost:5432/neurocards
   STORAGE_TYPE=local
   STORAGE_BASE_PATH=/var/neurocards/storage
   PUBLIC_DOMAIN=https://yourdomain.com
   ```

4. **Перезапустить сервисы:**
   ```bash
   systemctl restart neurocards-bot
   systemctl restart neurocards-worker
   ```

5. **Проверить статус:**
   ```bash
   ./scripts/monitor_vps.sh YOUR_SERVER_IP
   ```

### Вариант 2: Render + Supabase (managed)

1. **Создать проект в Supabase**
2. **Выполнить миграции** из `supabase/schema.sql`
3. **Создать buckets** в Supabase Storage: `inputs`, `outputs`
4. **Задеплоить на Render:**
   ```yaml
   # render.yaml
   services:
     - type: web
       name: neurocards-bot
       env: python
       buildCommand: pip install -r requirements.txt
       startCommand: python -m app.main
       envVars:
         - key: DATABASE_TYPE
           value: supabase
         - key: STORAGE_TYPE
           value: supabase
   ```

## ⚙️ Environment Variables

### Обязательные для обоих режимов
```bash
BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_key
KIE_API_KEY=your_kie_key
```

### Для PostgreSQL режима
```bash
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://user:pass@host:5432/dbname
STORAGE_TYPE=local
STORAGE_BASE_PATH=/var/neurocards/storage
PUBLIC_DOMAIN=https://yourdomain.com
```

### Для Supabase режима
```bash
DATABASE_TYPE=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key
STORAGE_TYPE=supabase
```

## 📊 Сравнение режимов

| Параметр | VPS (Self-Hosted) | Render + Supabase |
|----------|-------------------|-------------------|
| **Стоимость/месяц** | $5-10 | $25-50 |
| **Контроль** | Полный | Ограниченный |
| **Настройка** | Автоматическая (скрипт) | Ручная (UI) |
| **Масштабируемость** | Ручная (запуск worker'ов) | Автоматическая |
| **Бэкапы** | Ручные (скрипт) | Автоматические |
| **Latency** | Низкая (всё локально) | Средняя (сеть) |
| **Зависимость** | Нет | Render, Supabase |

## 🧪 Тестирование

### Проверить режим PostgreSQL:
```bash
DATABASE_TYPE=postgres DATABASE_URL=postgresql://... python -c "
from app.db_adapter import init_db_pool, get_or_create_user
import asyncio

async def test():
    await init_db_pool()
    user = await get_or_create_user(123456789)
    print(f'User: {user}')

asyncio.run(test())
"
```

### Проверить режим Supabase:
```bash
DATABASE_TYPE=supabase SUPABASE_URL=... python -c "
from app.db_adapter import get_or_create_user
import asyncio

async def test():
    user = await get_or_create_user(123456789)
    print(f'User: {user}')

asyncio.run(test())
"
```

## 📝 Документация

- [README.md](README.md) - Общий обзор проекта
- [SELF_HOSTING.md](SELF_HOSTING.md) - Полная инструкция по VPS деплою
- [QUICKSTART_VPS.md](QUICKSTART_VPS.md) - Быстрый старт за 15 минут
- [DATABASE_ADAPTER.md](DATABASE_ADAPTER.md) - Детали миграции БД
- [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md) - Миграции схемы
- [PARALLEL_WORKERS.md](PARALLEL_WORKERS.md) - Масштабирование

## 🎉 Итог

Теперь у вас есть:

✅ **Полная независимость** - можно работать без Supabase
✅ **Гибкость** - можно переключаться между режимами
✅ **Экономия** - VPS дешевле на $20/месяц
✅ **Производительность** - всё локально = быстрее
✅ **Контроль** - полный доступ к серверу и данным

Бот готов к production! 🚀
