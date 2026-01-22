# 🚀 ИНСТРУКЦИЯ ПО ДЕПЛОЮ

## Вариант 1: Через Git Pull (если SSH работает)

```bash
# На сервере
ssh root@146.19.214.97
cd /root/neurocards-bot

# Получить последние изменения
git fetch origin
git reset --hard origin/main
git pull origin main

# Перезапустить сервисы
systemctl restart neurocards-bot
systemctl restart neurocards-worker@{1..20}

# Проверить статус
systemctl status neurocards-bot
./scripts/manage_workers.sh status
```

## Вариант 2: Через патч (если Git push не работает)

```bash
# На сервере
cd /root/neurocards-bot

# Скопировать патч файл на сервер (scp/rsync/wget)
# Применить патч
git am < /tmp/0001-Complete-All-fixes-testing-deployment-ready.patch

# Или просто скопировать файлы вручную:
# Скопировать все файлы из локального репо на сервер

# Перезапустить
systemctl restart neurocards-bot
systemctl restart neurocards-worker@{1..20}
```

## Вариант 3: Прямое копирование файлов

```bash
# Скопировать эти файлы на сервер (заменить существующие):

app/handlers/menu_and_flow.py
app/db_adapter.py
worker/worker.py
worker/kie_client.py
worker/kie_key_rotator.py
worker/kie_error_classifier.py
scripts/manage_workers.sh
systemd/neurocards-worker@.service

# Затем перезапустить
systemctl daemon-reload
systemctl restart neurocards-bot
systemctl restart neurocards-worker@{1..20}
```

## После деплоя: Проверка

### 1. Проверить что сервисы запущены
```bash
systemctl status neurocards-bot
systemctl status neurocards-worker@1
./scripts/manage_workers.sh status
```

### 2. Проверить логи
```bash
# Бот
journalctl -u neurocards-bot -f

# Воркеры
journalctl -u neurocards-worker@1 -f

# Все воркеры
./scripts/manage_workers.sh logs
```

### 3. Начислить кредиты для тестирования
```bash
# Подключиться к PostgreSQL
psql $DATABASE_URL

# Начислить 100 кредитов
UPDATE users SET credits = credits + 100 WHERE tg_user_id = 5235703016;
\q
```

### 4. Проверить в Telegram
- Отправить /start
- Отправить фото
- Выбрать промпт
- Выбрать количество видео (1/3/5)
- Проверить что задачи создаются
- Проверить polling и получение результата

### 5. Проверить БД
```bash
psql $DATABASE_URL -c "SELECT status, COUNT(*) FROM generation_jobs GROUP BY status;"
psql $DATABASE_URL -c "SELECT id, status, created_at, started_at FROM generation_jobs ORDER BY id DESC LIMIT 5;"
```

## Environment Variables

Убедиться что на сервере есть все переменные:

```bash
# В /root/neurocards-bot/.env или в systemd
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://user:pass@localhost/dbname
BOT_TOKEN=<telegram_bot_token>
KIE_API_KEY=<kie_api_key>

# Опционально для ротации:
# KIE_API_KEY_1=...
# KIE_API_KEY_2=...
# KIE_API_KEY_3=...
```

## Масштабирование воркеров

```bash
# Запустить 20 воркеров
./scripts/manage_workers.sh start 20

# Остановить все
./scripts/manage_workers.sh stop

# Проверить статус
./scripts/manage_workers.sh status

# Посмотреть логи
./scripts/manage_workers.sh logs
```

## Troubleshooting

### Бот не отвечает
```bash
journalctl -u neurocards-bot -n 100 --no-pager
systemctl restart neurocards-bot
```

### Воркеры не обрабатывают задачи
```bash
# Проверить что воркеры запущены
systemctl list-units | grep neurocards-worker

# Проверить логи
journalctl -u neurocards-worker@1 -n 50 --no-pager

# Перезапустить
systemctl restart neurocards-worker@{1..20}
```

### Задачи застревают в queued
```bash
# Проверить очередь
psql $DATABASE_URL -c "SELECT COUNT(*) FROM generation_jobs WHERE status='queued';"

# Проверить что воркеры работают
./scripts/manage_workers.sh status

# Добавить больше воркеров если нужно
./scripts/manage_workers.sh start 30
```

### KIE API ошибки
```bash
# Проверить логи воркеров
journalctl -u neurocards-worker@1 -f | grep -i "kie\|error"

# Проверить что API ключи рабочие
# Обновить в .env если нужно
```

---

## 📊 Мониторинг

### Статистика генераций
```sql
-- Всего задач
SELECT COUNT(*) FROM generation_jobs;

-- По статусам
SELECT status, COUNT(*) FROM generation_jobs GROUP BY status;

-- За последний час
SELECT status, COUNT(*) FROM generation_jobs 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status;

-- Средняя длительность
SELECT 
    AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_seconds
FROM generation_jobs 
WHERE status = 'completed' 
    AND finished_at IS NOT NULL;
```

### Активность воркеров
```bash
# Сколько воркеров активны
systemctl list-units | grep neurocards-worker | grep running | wc -l

# Загрузка CPU/RAM
top -b -n 1 | grep python3

# Дисковое пространство
df -h /root/neurocards-bot
```

---

## ✅ CHECKLIST

- [ ] Код задеплоен на сервер
- [ ] Сервисы перезапущены
- [ ] Логи проверены (нет критичных ошибок)
- [ ] Environment variables настроены
- [ ] 20 воркеров запущены
- [ ] Кредиты начислены для тестирования
- [ ] Тест в Telegram: отправка фото → выбор промпта → генерация
- [ ] Проверка получения видео
- [ ] Проверка обработки ошибок
- [ ] Мониторинг настроен

**🎉 После выполнения всех пунктов - система готова к использованию!**
