# 🔍 ПОЛНЫЙ АУДИТ ПРОЕКТА NEUROCARDS-BOT

**Дата аудита:** 25 Jan 2026  
**Версия:** Commit b480593  
**Статус:** Production (со своими проблемами)

---

## 📊 СТРУКТУРА ПРОЕКТА

```
├── app/                    # Telegram bot (aiogram 3.24)
│   ├── main_polling.py    # ✅ Entry point (polling mode - БЕЗ webhook)
│   ├── main.py            # ❌ Webhook mode (не используется)
│   ├── config.py          # Config & env loading
│   ├── db_adapter.py      # ✅ PostgreSQL adapter (asyncpg)
│   ├── handlers/          # Message/callback handlers
│   │   ├── start.py       # /start command
│   │   ├── menu_and_flow.py # Inline menus
│   │   ├── flow_*.py      # Generation flows
│   │   └── fallback.py    # Unknown messages
│   ├── services/          # Business logic
│   │   ├── generation.py  # ✅ Job creation
│   │   ├── redis_queue.py # ✅ RQ queue adapter
│   │   └── storage_factory.py # Local storage
│   └── keyboards.py       # Inline buttons
│
├── worker/               # Video generation worker (async)
│   ├── worker.py        # ✅ Main worker loop (fetch → process → update)
│   ├── video_processor.py # ✅ Core: GPT prompt + KIE.AI + polling
│   ├── kie_client.py    # ✅ KIE.AI API wrapper (+ NEW logging!)
│   ├── kie_error_classifier.py # Error categorization
│   ├── openai_prompter.py # GPT prompt generation
│   └── kie_key_rotator.py  # API key rotation
│
├── supabase/
│   └── schema.sql       # ✅ PostgreSQL schema + functions
│
├── docker-compose.yml   # 🐳 Production orchestration
├── Dockerfile.bot       # Bot container
├── Dockerfile.worker    # Worker container
└── requirements.txt     # Python deps
```

---

## ✅ ЧТО РАБОТАЕТ

### **1. Bot (Polling Mode)**
- ✅ **Запущен на сервере:** `neurocards-polling` container
- ✅ **Режим:** Polling (не webhook) — проще для тестирования
- ✅ **Handlers:** /start, menu, generation flows работают
- ✅ **Database:** Подключение к PostgreSQL через asyncpg
- ✅ **User flow:** /start → Menu → /cabinet → /generation
- ✅ **Keyboard:** Inline buttons работают
- ✅ **Session storage:** MemoryStorage (FSMContext работает)

### **2. Worker (3 instances)**
- ✅ **Запущены:** worker-1, worker-2, worker-3
- ✅ **RQ integration:** Слушает очередь neurocards в Redis
- ✅ **Job processing:** Забирает → Обрабатывает → Обновляет БД
- ✅ **KIE.AI integration:** Создает задачи, полит результаты
- ✅ **Error handling:** Классификация ошибок (user_violation, billing, rate_limit, temporary)
- ✅ **Fallback logic:** При OpenAI 429 используется fallback prompt
- ✅ **NEW Logging:** Детальное логирование каждого polling цикла KIE

### **3. Database (PostgreSQL 15)**
- ✅ **Schema:** Таблицы users, jobs + indexes
- ✅ **Function:** create_job_and_consume_credit (атомарная операция)
- ✅ **Atomicity:** Транзакция гарантирует либо job+credit, либо nothing
- ✅ **Indexes:** На tg_user_id, status, created_at, idempotency_key
- ✅ **Pool:** asyncpg pool с min=2, max=10

### **4. Redis**
- ✅ **Queue:** rq:queue:neurocards (RQ standard)
- ✅ **Connectivity:** Контейнер живой, доступен
- ✅ **Data:** Jobs сохраняются как RQ Job objects

### **5. Docker Setup**
- ✅ **Compose:** Все сервисы поднимаются успешно
- ✅ **Networks:** Все контейнеры в одной сети (service discovery работает)
- ✅ **Healthchecks:** PostgreSQL, Redis, Bot healthy
- ✅ **Environment:** DATABASE_URL правильно передается

---

## ❌ ЧТО НЕ РАБОТАЕТ / ПРОБЛЕМЫ

### **1. КРИТИЧНАЯ: Кредиты не добавляются**

**Проблема:**
```python
# app/db_adapter.py:291
async def refund_credit(tg_user_id: int) -> None:
    """Возвращает 1 кредит пользователю"""
    if DATABASE_TYPE == "postgres":
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "SELECT refund_credit($1)",  # ← Вызывает функцию БД
                tg_user_id
            )
```

**НО:** В `supabase/schema.sql` функция `refund_credit()` **НЕ ОПРЕДЕЛЕНА!**

Результат:
- ❌ Код вызывает `SELECT refund_credit($1)` → **SQL error: function does not exist**
- ❌ Кредиты НЕ возвращаются при ошибках
- ❌ User теряет кредит и не получает ничего

### **2. Нет функции добавления кредитов вообще**

**Проблема:**
- Есть /cabinet → "💳 Пополнить баланс" кнопка
- Но это STUB! Нет реальной логики пополнения
- `@router.callback_query(F.data.startswith("pay:"))` → просто сообщение "в разработке"

**Результат:**
- ❌ Пользователь кликает "пополнить" → НИЧЕГО НЕ ПРОИСХОДИТ
- ❌ Нет взаимодействия с платежной системой
- ❌ Пользователи на 0 кредитов "застревают"

### **3. OpenAI Quota Exceeded**

**Проблема:**
- Ваш OpenAI API ключ исчерпал лимит
- Статус: `insufficient_quota`

**Текущее состояние:**
- ✅ Fallback prompt работает ("A commercial video showing: ...")
- ❌ Но fallback слишком простой → KIE.AI может отказать
- ❌ Нет денег на OpenAI → генерация запросов будет падать

### **4. Проблема с Sora-2 / KIE.AI**

**Проблема:**
- Задача 6510aa4c "зависла" на 3+ часа в `processing`
- KIE вернула ошибку, но worker её не залогировал должным образом

**Решение:**
- ✅ Добавил логирование каждого polling цикла (commit 81cfa41)
- ✅ Теперь видно будет `failMsg` и `failCode` от KIE
- ⏳ Нужна полная статистика для анализа

### **5. Нет локального теста бота**

**Проблема:**
- Бот может запуститься локально в polling режиме
- **НО:** Нужен реальный TELEGRAM_BOT_TOKEN
- PostgreSQL/Redis доступны в Docker Compose
- ❌ Не может быть полностью автономно протестирован без reals Telegram

**Возможное решение:**
- Создать mock Telegram updates для unit тестов
- Или использовать тестовый бот токен

### **6. 1 Worker может зависнуть → остальные два не помогут**

**Текущее:** 3 worker'а на одной очереди
**Проблема:** Если worker-1 зависает на 30 мин, job остается в "processing"
- ❌ Нет timeout mechanism
- ❌ Нет restart логики для stuck jobs
- ❌ Если все 3 зависнут → очередь заблокирована

---

## 🗄️ ДЕТАЛИ БД

### **Users Table**
```sql
id UUID PRIMARY KEY
tg_user_id BIGINT UNIQUE  -- Telegram user ID (индексирован)
username TEXT
credits INT DEFAULT 0     -- ← КЛЮЧЕВОЕ ПОЛЕ ДЛЯ ПРОБЛЕМЫ
created_at TIMESTAMP
```

**Проблема:** Когда пользователь создается → 2 кредита. Но:
- ❌ Нет функции `add_credits(tg_user_id, amount)`
- ❌ Нет функции `topup_user(tg_user_id, stripe_id)` для платежей
- ❌ `refund_credit()` функция НЕ СУЩЕСТВУЕТ в БД

### **Jobs Table**
```sql
id TEXT PRIMARY KEY       -- UUID как string
status TEXT CHECK (queued, processing, completed, failed)
credits_deducted INT DEFAULT 1
kie_task_id TEXT         -- ID в KIE.AI
video_url TEXT
error TEXT, error_details JSONB
```

**Хорошее:**
- ✅ Idempotency key + unique index
- ✅ Все необходимые поля есть

**Проблема:**
- ❌ `error_details JSONB` заполняется, но **не логируется в приложении**
- ❌ Когда job fails → информация об ошибке не попадает в app

---

## 📋 ЧТО НУЖНО СДЕЛАТЬ (TODO)

### **Phase 1: FIX CRITICAL (СЕЙЧАС)**

**Priority 1: Кредиты**
```sql
-- НУЖНО ДОБАВИТЬ В schema.sql:
CREATE OR REPLACE FUNCTION refund_credit(p_tg_user_id BIGINT)
RETURNS VOID AS $$
BEGIN
    UPDATE users SET credits = credits + 1 WHERE tg_user_id = p_tg_user_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION add_credits(p_tg_user_id BIGINT, p_amount INT)
RETURNS INT AS $$
DECLARE
    v_new_credits INT;
BEGIN
    UPDATE users 
    SET credits = credits + p_amount, updated_at = NOW() 
    WHERE tg_user_id = p_tg_user_id 
    RETURNING credits INTO v_new_credits;
    RETURN v_new_credits;
END;
$$ LANGUAGE plpgsql;
```

**Priority 2: Реализовать топап логику**
- [ ] Реальная платежная система (Stripe/YooKassa)
- [ ] Callback handler для платежей
- [ ] Webhook для подтверждения платежей

### **Phase 2: STABILIZE WORKER (1-2 недели)**

**Priority 1: Worker timeout**
```python
# worker/worker.py: добавить timeout для каждой job
max_job_age = 15 * 60  # 15 минут
if job.created_at < (time.time() - max_job_age):
    job.status = "failed"
    job.error = "Worker timeout: job stuck for 15+ min"
    # Возвращаем кредит, уведомляем user
```

**Priority 2: Мониторинг KIE.AI ошибок**
- ✅ Логирование улучшено (commit 81cfa41)
- [ ] Добавить метрики в БД
- [ ] Dashboard для анализа ошибок

**Priority 3: Один worker полностью**
- [ ] Запустить ТОЛЬКО worker-1
- [ ] Прогнать 10-20 полных циклов генерации
- [ ] Логировать ВСЕ ошибки, edge cases
- [ ] Убедиться что всегда возвращает результат или ошибку
- [ ] ПОТОМ масштабировать на 3

### **Phase 3: LOCAL TESTING**

**Priority 1: Local bot launch**
```bash
# Нужно сделать возможным:
$ export DATABASE_URL=postgresql://user:pass@localhost:5432/neurocards
$ export REDIS_URL=redis://localhost:6379
$ export BOT_TOKEN=<test_bot_token>
$ python -m app.main_polling
# ✅ Бот запускается, готов к тестированию
```

**Priority 2: Unit tests**
- [ ] Mock Telegram updates
- [ ] Test job creation flow
- [ ] Test credit deduction
- [ ] Test worker processing

---

## 🛠️ РЕКОМЕНДАЦИИ

### **Для вас (пользователя):**

**1. Немедленно:**
- [ ] Добавить `refund_credit()` и `add_credits()` функции в БД
- [ ] Протестировать работу возврата кредитов

**2. Эта неделя:**
- [ ] Запустить ТОЛЬКО worker-1, убедиться стабильность
- [ ] Пополнить OpenAI quota (или использовать другой API ключ)
- [ ] Прогнать 20+ полных циклов генерации

**3. Следующая неделя:**
- [ ] Реализовать базовую платежную систему (даже простую)
- [ ] Добавить timeout для worker jobs
- [ ] Настроить локальный запуск бота для разработки

### **Для архитектуры:**

**Current:**
```
Bot (polling) → Redis Queue → Worker(s) × 3 → KIE.AI
      ↓
  PostgreSQL
```

**Recommendation:**
```
Bot (polling) → Redis Queue → Worker (1 stable) → KIE.AI
      ↓              ↓
  PostgreSQL    Job Monitor (timeout detection)
      ↓
  Payment System (Stripe/YooKassa)
```

---

## 💾 ФАЙЛЫ ДЛЯ ДЕЙСТВИЯ

**Нужно поправить:**
1. `supabase/schema.sql` — добавить refund_credit() и add_credits()
2. `app/handlers/menu_and_flow.py` — реализовать топап логику
3. `worker/worker.py` — добавить timeout для stuck jobs
4. `requirements-dev.txt` — создать для локальной разработки

**Уже исправлено:**
✅ `worker/kie_client.py` — NEW logging (commit 81cfa41)
✅ `worker/video_processor.py` — NEW logging (commit 81cfa41)
✅ `docker-compose.yml` — DATABASE_URL правильный
✅ `app/main_polling.py` — polling mode активен

---

## 🎯 ЗАКЛЮЧЕНИЕ

**Состояние проекта:** 70% готов

**Что работает:**
- ✅ Bot + Workers + DB + Redis = интегрированы
- ✅ Генерация видео = основной flow работает
- ✅ Ошибка обработка = нужны доработки, но логика есть

**Что сломано:**
- ❌ Кредиты = нет функций в БД
- ❌ Платежи = вообще не реализованы
- ❌ OpenAI = нет денег
- ❌ Worker stability = нет timeout защиты

**Рекомендация:**
Сначала **один worker** полностью довести до ума, потом масштабировать.
Параллельно добавить 2-3 SQL функции для кредитов.

---

**Дальше:** Начнем с Phase 1 — исправим БД кредиты?
