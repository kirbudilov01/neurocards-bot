# Параллельный Worker для массовых генераций

## Проблема
При большом количестве заказов (100+ в день) один worker будет медленно обрабатывать очередь.

## Решение 1: Несколько worker процессов (РЕКОМЕНДУЕТСЯ)

На Render можно запустить несколько инстансов worker сервиса:

1. **Dashboard → neurocards-worker → Settings → Instance Count**
2. Установите например **3 instances**
3. Render автоматически запустит 3 копии worker'а

### Как это работает:
- Каждый worker опрашивает БД независимо
- PostgreSQL гарантирует что один job берется только одним worker'ом (благодаря `FOR UPDATE`)
- Все worker'ы обрабатывают очередь параллельно

### Преимущества:
✅ Простота - без изменений кода
✅ Надежность - если один worker упал, другие продолжают работу
✅ Масштабируемость - легко добавить больше instances

### Недостатки:
⚠️ Стоимость - каждый instance стоит отдельно на Render
⚠️ Возможны редкие race conditions (минимальные)

## Решение 2: SKIP LOCKED (оптимальное)

Добавить `SKIP LOCKED` в SQL запрос для гарантированной параллельной работы:

```python
# worker/worker.py
def fetch_next_queued_job():
    try:
        # С SKIP LOCKED - безопасно для параллельных worker'ов
        res = (
            supabase.table("jobs")
            .select("*")
            .eq("status", "queued")
            .order("created_at", desc=False)
            .limit(1)
            # TODO: Supabase Python SDK не поддерживает SKIP LOCKED напрямую
            # Нужно использовать raw SQL
            .execute()
        )
```

### Использование raw SQL:
```python
def fetch_next_queued_job():
    try:
        # Raw SQL с SKIP LOCKED
        query = """
            SELECT * FROM jobs 
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """
        res = supabase.rpc("exec_sql", {"query": query}).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"❌ Error fetching next job: {e}", exc_info=True)
        return None
```

Нужна RPC функция в Supabase:
```sql
CREATE OR REPLACE FUNCTION exec_sql(query TEXT)
RETURNS SETOF json
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY EXECUTE query;
END;
$$;
```

## Решение 3: Batch processing в одном worker

Обрабатывать несколько задач параллельно в рамках одного worker процесса:

```python
async def main():
    bot = Bot(BOT_TOKEN)
    max_concurrent = 3  # Обрабатывать 3 задачи одновременно
    
    tasks = []
    while not shutdown_flag:
        # Собираем пул задач
        while len(tasks) < max_concurrent:
            job = fetch_next_queued_job()
            if job:
                task = asyncio.create_task(process_job(bot, job))
                tasks.append(task)
            else:
                break
        
        if not tasks:
            await asyncio.sleep(2)
            continue
        
        # Ждем завершения хотя бы одной задачи
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Обновляем список активных задач
        tasks = list(pending)
```

## Рекомендация для вашего случая

Для 100+ генераций в день:

1. **Старт:** Используйте **Решение 1** (3 instances на Render)
   - Просто, надежно, без изменений кода
   - 3 worker'а могут обрабатывать ~1500 задач в день (при 5 мин/задача)

2. **Рост:** При >300 генераций/день добавьте **Решение 2** (SKIP LOCKED)
   - Полностью исключает race conditions
   - Позволяет масштабировать до 10+ worker'ов

3. **Будущее:** При >1000 генераций/день - отдельная очередь (RabbitMQ/Redis)

## Мониторинг

Добавьте endpoint для проверки очереди:

```python
# app/main.py
async def handle_queue_stats(request):
    queued = supabase.table("jobs").select("id", count="exact").eq("status", "queued").execute()
    processing = supabase.table("jobs").select("id", count="exact").eq("status", "processing").execute()
    
    return web.json_response({
        "queued": queued.count,
        "processing": processing.count,
        "workers": 1  # или количество instances
    })

app.router.add_get("/queue", handle_queue_stats)
```

Тогда можно мониторить: `curl https://your-bot.onrender.com/queue`
