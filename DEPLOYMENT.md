# Инструкция по деплою на Render.com

## Описание проекта

Telegram-бот для генерации вертикальных видео (Reels/TikTok) из фото товаров с помощью AI:
- **KIE.AI API** - генерация видео (Sora-2)
- **OpenAI GPT** - генерация промптов
- **Supabase** - база данных + хранилище файлов
- **Aiogram 3** - фреймворк для Telegram бота

## Архитектура

Проект состоит из двух сервисов:

1. **neurocards-bot** (Web Service) - основной Telegram бот, обрабатывает webhook
2. **neurocards-worker** (Worker) - фоновый процесс для генерации видео

## Настройка на Render

### 1. Подключение репозитория

1. Зайдите на https://render.com
2. Нажмите "New" → "Blueprint"
3. Подключите ваш GitHub репозиторий `kirbudilov01/neurocards-bot`
4. Render автоматически обнаружит `render.yaml` и создаст оба сервиса

### 2. Настройка переменных окружения

#### Для обоих сервисов (Bot + Worker):

**Обязательные:**
```bash
BOT_TOKEN=your_telegram_bot_token
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

**Для бота (Web Service):**
```bash
PUBLIC_BASE_URL=https://neurocards-bot.onrender.com
WEBHOOK_SECRET_TOKEN=any_random_secret_string
```

**Для воркера (Worker):**
```bash
KIE_API_KEY=your_kie_api_key
OPENAI_API_KEY=your_openai_api_key
```

### 3. Получение токенов

#### Telegram Bot Token
1. Найдите @BotFather в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Скопируйте полученный токен

#### Supabase
1. Зайдите на https://supabase.com
2. Создайте новый проект
3. Перейдите в Settings → API
4. Скопируйте:
   - URL проекта
   - service_role key (не anon key!)

#### KIE.AI API Key
1. Зарегистрируйтесь на https://kie.ai
2. Получите API ключ в личном кабинете

#### OpenAI API Key
1. Зайдите на https://platform.openai.com
2. Создайте новый API ключ в разделе API keys

### 4. Настройка базы данных Supabase

Выполните миграции из папки `supabase/migrations/`:

1. Откройте Supabase SQL Editor
2. Выполните по очереди:
   - `20240722120000_atomicity_and_idempotency.sql`
   - `20240723120000_add_unique_index_on_tg_user_id.sql`
3. Создайте storage buckets:
   - `inputs` (для загружаемых фото)
   - `outputs` (для готовых видео)

### 5. Деплой

После настройки переменных окружения:
1. Render автоматически задеплоит оба сервиса
2. При каждом push в main ветку произойдет автоматический редеплой
3. Проверьте логи в Render Dashboard

## Мониторинг

### Health Checks

- Bot: `https://your-bot-url.onrender.com/healthz`
- Возвращает `ok` если бот работает

### Логи

Все критичные события логируются:
- ✅ Успешные операции
- ⚠️ Предупреждения
- ❌ Ошибки

Логи можно смотреть в Render Dashboard для каждого сервиса.

### Типичные проблемы и решения

#### Бот не запускается
- Проверьте переменные окружения
- Убедитесь что `BOT_TOKEN` и `PUBLIC_BASE_URL` установлены
- Проверьте логи на наличие ошибок

#### Генерация не работает
- Проверьте что Worker запущен
- Убедитесь что `KIE_API_KEY` и `OPENAI_API_KEY` установлены
- Проверьте баланс API ключей
- Посмотрите логи Worker'а

#### Видео получаются квадратные
- ✅ Исправлено: `aspect_ratio` теперь `9:16`
- Если проблема осталась, проверьте версию KIE.AI API

#### Задачи зависают
- Таймаут увеличен до 6 минут
- Worker автоматически переподключается при ошибках
- Максимум 5 последовательных ошибок до перезапуска

## Обновление

После внесения изменений в код:

```bash
git add .
git commit -m "your message"
git push origin main
```

Render автоматически:
1. Обнаружит изменения
2. Пересоберет сервисы
3. Перезапустит их с zero-downtime

## Поддержка

При возникновении проблем:
1. Проверьте логи в Render Dashboard
2. Убедитесь что все переменные окружения установлены
3. Проверьте баланс API ключей (KIE.AI, OpenAI)
4. Посмотрите таблицу `jobs` в Supabase для отладки

## Масштабирование

Для увеличения производительности:
1. Увеличьте план Render (Starter → Standard)
2. Worker может обрабатывать задачи последовательно
3. Для параллельной обработки нужно несколько Worker'ов (требуется SKIP LOCKED в SQL)
