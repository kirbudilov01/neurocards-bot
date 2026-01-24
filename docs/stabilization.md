# Стабилизация (дневник изменений)

## 2026-01-24
- Добавлен `idempotency_key` в таблицу `jobs` + индекс, применено в прод БД (фикc UndefinedColumn).
- Бот переведён на polling, токен обновлён; webhook удалён.
- В образ бота включены `assets/`, привет-видео отправляется по `WELCOME_VIDEO_FILE_ID` (кастомный env).
- Supabase ветки убраны, `DATABASE_TYPE` по умолчанию `postgres`, `USE_POSTGRES=true`.
- Healthcheck бота упрощён, работает без psycopg2; compose/окружение синхронизировано.
