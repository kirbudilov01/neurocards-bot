# Миграция с Supabase на локальную БД

## Зачем переходить на локальную БД?

✅ Полный контроль над данными
✅ Нет лимитов Supabase бесплатного плана
✅ Быстрее для локальной разработки
✅ Дешевле при больших объемах

## Вариант 1: PostgreSQL на Render (РЕКОМЕНДУЕТСЯ)

### Шаг 1: Создать PostgreSQL на Render

1. Dashboard → New → PostgreSQL
2. Name: `neurocards-db`
3. Plan: Starter ($7/month, 1GB)
4. Create Database

Render даст вам:
```
Internal Database URL: postgresql://...
External Database URL: postgresql://...
```

### Шаг 2: Применить миграции

```bash
# Установить psql локально
# Mac: brew install postgresql
# Ubuntu: sudo apt install postgresql-client

# Подключиться к БД
psql "postgresql://user:password@hostname/database"

# Выполнить миграции по порядку:
\i supabase/schema.sql
\i supabase/migrations/20240722120000_atomicity_and_idempotency.sql
\i supabase/migrations/20240723120000_add_unique_index_on_tg_user_id.sql
\i supabase/migrations/20260118000000_fix_credits_and_defaults.sql
```

### Шаг 3: Обновить environment variables

В Render для обоих сервисов (bot + worker):

```bash
# Заменить Supabase переменные на:
DATABASE_URL=postgresql://...  # Internal URL от Render
```

### Шаг 4: Обновить код

Заменить Supabase client на asyncpg:

```bash
# requirements.txt
# Удалить: supabase==2.*
# Добавить:
asyncpg==0.29.*
```

```python
# app/db.py
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")
pool = None

async def get_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

async def get_or_create_user(tg_user_id: int, username: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Проверить существующего пользователя
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE tg_user_id = $1",
            tg_user_id
        )
        
        if row:
            # Обновить username если нужно
            if username and row['username'] != username:
                await conn.execute(
                    "UPDATE users SET username = $1 WHERE tg_user_id = $2",
                    username, tg_user_id
                )
            return dict(row)
        
        # Создать нового пользователя
        row = await conn.fetchrow(
            "INSERT INTO users (tg_user_id, username, credits) "
            "VALUES ($1, $2, 2) RETURNING *",
            tg_user_id, username
        )
        return dict(row)

async def create_job_and_consume_credit(...):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM create_job_and_consume_credit($1, $2, $3, $4, $5, $6, $7)",
            tg_user_id, idempotency_key, kind, input_photo_path,
            json.dumps(product_info), extra_wishes, template_id
        )
        return {"job_id": row['job_id'], "new_credits": row['new_credits']}
```

### Шаг 5: Storage для файлов

Render не предоставляет S3-like storage. Варианты:

**A. Cloudflare R2** (рекомендуется - дешево)
```bash
pip install boto3

# .env
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT=https://...r2.cloudflarestorage.com
R2_BUCKET_NAME=neurocards
```

**B. AWS S3**
**C. DigitalOcean Spaces**
**D. Supabase Storage** (оставить только storage, БД на Render)

## Вариант 2: SQLite (только для тестирования)

НЕ рекомендуется для production, но для локальной разработки:

```python
import aiosqlite

async def init_db():
    async with aiosqlite.connect('neurocards.db') as db:
        # Создать таблицы
        await db.executescript(open('supabase/schema.sql').read())
        await db.commit()
```

## Вариант 3: Оставить Supabase, но оптимизировать

Если хотите остаться на Supabase:

1. **Проверьте текущий план:**
   - Free: 500MB БД, 1GB storage
   - Pro: $25/month, неограниченно

2. **Оптимизируйте:**
   - Удаляйте старые jobs (>30 дней)
   - Храните только URL видео, не сами файлы в БД
   - Используйте indexes (уже добавлены в schema.sql)

3. **Мониторинг:**
   ```sql
   -- Проверить размер БД
   SELECT pg_size_pretty(pg_database_size('postgres'));
   
   -- Проверить топ таблиц
   SELECT
     schemaname,
     tablename,
     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
   FROM pg_tables
   WHERE schemaname = 'public'
   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
   ```

## Миграция данных

Если уже есть пользователи на Supabase:

```bash
# Экспорт из Supabase
pg_dump "postgresql://...supabase..." > backup.sql

# Импорт в новую БД
psql "postgresql://...render..." < backup.sql
```

Или через Python:
```python
import asyncpg
from supabase import create_client

# Старая БД (Supabase)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Новая БД (Render)
new_conn = await asyncpg.connect(DATABASE_URL)

# Миграция users
users = supabase.table("users").select("*").execute()
for user in users.data:
    await new_conn.execute(
        "INSERT INTO users (id, tg_user_id, username, credits, created_at) "
        "VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (tg_user_id) DO NOTHING",
        user['id'], user['tg_user_id'], user['username'], 
        user['credits'], user['created_at']
    )

# Миграция jobs (только активные)
jobs = supabase.table("jobs").select("*").in_("status", ["queued", "processing"]).execute()
# ... аналогично
```

## Рекомендация

Для вашего случая (бот растет, нужна стабильность):

**Оптимальный вариант:**
1. **БД:** PostgreSQL на Render ($7/month)
2. **Storage:** Cloudflare R2 (почти бесплатно, $0.015/GB)
3. **Миграция:** Постепенная - новые пользователи на новую БД

**Альтернатива (если бюджет ограничен):**
1. Остаться на Supabase Free tier
2. Добавить cleanup старых jobs
3. Апгрейд до Pro ($25) когда будет >1000 активных пользователей

## Что делать сейчас?

1. **Срочно:** Исправить баг с credits
   - Выполнить миграцию `20260118000000_fix_credits_and_defaults.sql` в Supabase
   - Проверить что у новых пользователей credits = 2

2. **Мониторинг:** Добавить логи
   ```python
   logger.info(f"User {tg_user_id} has {credits} credits")
   ```

3. **Решение на будущее:**
   - Если >100 активных пользователей → Render PostgreSQL
   - Если <100 → остаться на Supabase, исправить баги
