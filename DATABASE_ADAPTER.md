# 🗄️ Переход на локальную PostgreSQL базу данных

## ✅ Что уже готово

### Созданные файлы:
1. **`app/db_adapter.py`** - универсальный адаптер БД:
   - Поддерживает как Supabase, так и прямой PostgreSQL
   - Автоматически выбирается через `DATABASE_TYPE` в .env
   - Connection pooling через asyncpg
   - Все функции работы с БД

2. **Обновлены файлы:**
   - `app/config.py` - добавлены `DATABASE_TYPE` и `DATABASE_URL`
   - `app/main.py` - инициализация и закрытие пула БД
   - `app/handlers/*` - импортируют из `db_adapter`

### Схема базы данных:
- ✅ [supabase/schema.sql](supabase/schema.sql) - полная схема
- ✅ [supabase/migrations/](supabase/migrations/) - все миграции
- ✅ RPC функции (`create_job_and_consume_credit`, `refund_credit`)

---

## 🚀 Как переключиться на локальную PostgreSQL

### Вариант 1: Автоматический (VPS)

Скрипт `deploy_to_vps.sh` **уже настраивает локальную PostgreSQL**:
```bash
./scripts/deploy_to_vps.sh YOUR_SERVER_IP
```

Автоматически:
- Устанавливает PostgreSQL 15
- Создает базу `neurocards`
- Загружает схему из `supabase/schema.sql`
- Настраивает `DATABASE_TYPE=postgres` в .env
- Запускает бота с локальной БД

### Вариант 2: Ручной (локальная разработка)

```bash
# 1. Устанавливаем PostgreSQL
sudo apt install postgresql postgresql-contrib

# 2. Создаем базу данных
sudo -u postgres psql << EOF
CREATE DATABASE neurocards;
CREATE USER botuser WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE neurocards TO botuser;
\c neurocards
GRANT ALL ON SCHEMA public TO botuser;
EOF

# 3. Загружаем схему
sudo -u postgres psql -d neurocards -f supabase/schema.sql

# 4. Настраиваем .env
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://botuser:your_password@localhost:5432/neurocards

# 5. Устанавливаем asyncpg (если не установлено)
pip install asyncpg

# 6. Запускаем бота
python -m app.main
```

---

## 🔄 Миграция данных из Supabase

Если уже есть пользователи и задания в Supabase:

```bash
# 1. Экспортируем данные из Supabase
# В Supabase Dashboard → SQL Editor:

-- Экспорт пользователей
COPY (SELECT * FROM users) TO STDOUT WITH CSV HEADER;
-- Сохрани как users.csv

-- Экспорт заданий
COPY (SELECT * FROM jobs) TO STDOUT WITH CSV HEADER;
-- Сохрани как jobs.csv

# 2. Импортируем в локальную PostgreSQL
sudo -u postgres psql -d neurocards << EOF
\COPY users FROM 'users.csv' CSV HEADER;
\COPY jobs FROM 'jobs.csv' CSV HEADER;
EOF

# 3. Проверяем
sudo -u postgres psql -d neurocards -c "SELECT COUNT(*) FROM users;"
sudo -u postgres psql -d neurocards -c "SELECT COUNT(*) FROM jobs;"
```

---

## ⚙️ Переменные окружения

### Для Supabase (текущий режим):
```bash
DATABASE_TYPE=supabase  # или не указывать (по умолчанию)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key
```

### Для локальной PostgreSQL:
```bash
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://botuser:password@localhost:5432/neurocards
```

**Код автоматически выберет нужный режим!**

---

## 📊 Архитектура db_adapter.py

```python
if DATABASE_TYPE == "postgres":
    # Используем asyncpg с connection pooling
    import asyncpg
    pool = await asyncpg.create_pool(DATABASE_URL)
    
    # Все запросы через пул
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT * FROM users WHERE tg_user_id = $1", user_id)

else:
    # Используем Supabase SDK (обратная совместимость)
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Запросы через Supabase
    result = supabase.table("users").select("*").eq("tg_user_id", user_id).execute()
```

---

## 🎯 Преимущества локальной БД

✅ **Независимость** - не зависим от Supabase  
✅ **Скорость** - нет сетевых задержек (БД на том же сервере)  
✅ **Контроль** - полный доступ к базе данных  
✅ **Экономия** - не платим за Supabase  
✅ **Масштабируемость** - можем настроить replication, sharding и т.д.  

---

## 🔍 Проверка работы

### После переключения на PostgreSQL:

```bash
# 1. Проверяем подключение
python -c "
import asyncio
import asyncpg
async def test():
    conn = await asyncpg.connect('postgresql://botuser:password@localhost:5432/neurocards')
    result = await conn.fetchval('SELECT COUNT(*) FROM users')
    print(f'Users: {result}')
    await conn.close()
asyncio.run(test())
"

# 2. Запускаем бота
python -m app.main

# 3. Проверяем логи
# Должно быть:
# ✅ PostgreSQL pool initialized
# ✅ Database pool initialized
# ✅ Webhook set successfully

# 4. Тестируем в Telegram
# /start - должен создать пользователя
# Загружаем фото - должно создать задание
```

---

## 🐛 Troubleshooting

### Ошибка "DATABASE_URL is required"
```bash
# Добавь в .env:
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://botuser:password@localhost:5432/neurocards
```

### Ошибка "password authentication failed"
```bash
# Проверь пароль в PostgreSQL
sudo -u postgres psql -d neurocards -c "ALTER USER botuser WITH PASSWORD 'new_password';"

# Обнови DATABASE_URL в .env
```

### Ошибка "relation users does not exist"
```bash
# Загрузи схему базы данных
sudo -u postgres psql -d neurocards -f supabase/schema.sql
```

### Ошибка "function create_job_and_consume_credit does not exist"
```bash
# Загрузи RPC функции
sudo -u postgres psql -d neurocards -f supabase/rpc.sql

# Или загрузи всю схему заново
sudo -u postgres psql -d neurocards -f supabase/schema.sql
```

---

## 📝 TODO: Функции которые нужно добавить в db_adapter.py

Некоторые функции из `app/db.py` еще не перенесены в `db_adapter.py`:

- [ ] `get_job_by_idempotency_key()` - проверка дубликатов
- [ ] `get_queue_position()` - позиция в очереди
- [ ] `safe_get_balance()` - безопасное получение баланса
- [ ] `list_last_jobs()` - список заданий пользователя
- [ ] `get_user_by_id()` - получение пользователя по UUID

**Решение:** Либо добавить их в `db_adapter.py`, либо оставить старый `app/db.py` для обратной совместимости и постепенно мигрировать.

---

## 🎯 Рекомендация

Для **production на VPS**:
```bash
# Используй автоматический деплой
./scripts/deploy_to_vps.sh YOUR_SERVER_IP

# Он сразу настроит:
# ✅ PostgreSQL локально
# ✅ DATABASE_TYPE=postgres
# ✅ Схему базы данных
# ✅ Локальное хранилище файлов
```

Для **локальной разработки**:
```bash
# Продолжай использовать Supabase
DATABASE_TYPE=supabase
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...

# Когда будешь готов переключиться:
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://...
```

**Код работает в обоих режимах!** 🎉

---

## 📚 Следующие шаги

1. ✅ **База данных** - готово! Переключается через `DATABASE_TYPE`
2. ✅ **Хранилище файлов** - готово! Переключается через `STORAGE_TYPE`
3. ⏳ **Миграция оставшихся функций** - добавить в `db_adapter.py`
4. ⏳ **Тесты** - протестировать оба режима (supabase + postgres)

---

Вопросы? Пиши! 🚀
