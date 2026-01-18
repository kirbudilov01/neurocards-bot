# 🚀 Быстрый старт: от нуля до запуска за 15 минут

Самый простой и дешевый способ запустить бота на своем сервере.

## 📋 Что нужно

1. **VPS сервер** (рекомендуем Hetzner CPX21 - €4.51/мес):
   - 2+ CPU cores
   - 4 GB RAM
   - 50 GB SSD
   - Ubuntu 22.04/24.04 LTS
   
2. **API ключи**:
   - Telegram Bot Token (от @BotFather)
   - KIE.AI API Key
   - OpenAI API Key

3. **Локальная машина** с SSH клиентом

---

## ⚡ Установка за 5 шагов

### 1️⃣ Создаем VPS

**Hetzner (рекомендуем):**
1. Регистрируемся на https://www.hetzner.com/cloud
2. Создаем новый проект
3. Выбираем: Cloud → Add Server
4. Локация: любая (рекомендуем Германия/Финляндия)
5. Image: Ubuntu 24.04
6. Type: CPX21 (3 vCPU, 4 GB RAM) - €4.51/мес
7. SSH Key: загружаем свой публичный ключ или создаем новый
8. Запускаем сервер
9. Копируем IP адрес

**Альтернативы:**
- DigitalOcean: https://www.digitalocean.com (~$6/мес)
- Vultr: https://www.vultr.com (~$6/мес)

---

### 2️⃣ Клонируем репозиторий локально

```bash
git clone https://github.com/YOUR_USERNAME/neurocards-bot.git
cd neurocards-bot
```

---

### 3️⃣ Запускаем автоматический деплой

```bash
# Делаем скрипт исполняемым
chmod +x scripts/deploy_to_vps.sh

# Запускаем деплой (замените YOUR_SERVER_IP на IP вашего сервера)
./scripts/deploy_to_vps.sh YOUR_SERVER_IP
```

**Скрипт запросит у вас:**
- BOT_TOKEN - токен от @BotFather
- WEBHOOK_URL - https://YOUR_SERVER_IP:8443/webhook (или домен)
- KIE_API_KEY - ключ от KIE.AI
- OPENAI_API_KEY - ключ от OpenAI

**Что произойдет автоматически:**
- ✅ Обновление системы
- ✅ Установка Python 3.11, PostgreSQL, Nginx
- ✅ Настройка firewall
- ✅ Создание базы данных
- ✅ Клонирование репозитория
- ✅ Установка зависимостей
- ✅ Настройка systemd сервисов
- ✅ Запуск бота и worker'а

⏱️ **Время выполнения:** 5-10 минут

---

### 4️⃣ Настраиваем Telegram webhook

```bash
# Замените BOT_TOKEN и YOUR_SERVER_IP
curl -X POST "https://api.telegram.org/botBOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://YOUR_SERVER_IP:8443/webhook"}'

# Проверяем webhook
curl "https://api.telegram.org/botBOT_TOKEN/getWebhookInfo"
```

Должен вернуться ответ с:
```json
{
  "ok": true,
  "result": {
    "url": "https://YOUR_SERVER_IP:8443/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

---

### 5️⃣ Тестируем бота

1. Открываем Telegram
2. Находим своего бота
3. Отправляем `/start`
4. Должны получить приветствие
5. Пробуем создать видео!

---

## 🎯 Готово! Бот работает

Теперь можно:

### 📊 Мониторить состояние
```bash
./scripts/monitor_vps.sh YOUR_SERVER_IP
```

### 🔄 Обновлять бота
```bash
# Сначала пушим изменения в GitHub
git add .
git commit -m "Update"
git push

# Потом обновляем на сервере
./scripts/update_vps.sh YOUR_SERVER_IP
```

### 💾 Делать бэкапы
```bash
./scripts/backup_vps.sh YOUR_SERVER_IP ./backups
```

### 📝 Смотреть логи
```bash
# Подключаемся к серверу
ssh botuser@YOUR_SERVER_IP

# Логи бота
sudo journalctl -u neurocards-bot -f

# Логи worker'а
sudo journalctl -u neurocards-worker@1 -f

# Все логи вместе
sudo journalctl -u neurocards-bot -u 'neurocards-worker@*' -f
```

---

## 🔥 Масштабирование (для высокой нагрузки)

Если генерируете много видео одновременно, можно запустить несколько worker'ов:

```bash
# Подключаемся к серверу
ssh root@YOUR_SERVER_IP

# Запускаем 3 worker'а параллельно
systemctl enable neurocards-worker@{2..3}
systemctl start neurocards-worker@{2..3}

# Проверяем
systemctl status 'neurocards-worker@*'
```

Теперь 3 worker'а будут обрабатывать задачи одновременно!

---

## ❓ Проблемы?

### Бот не отвечает

```bash
# Проверяем статус
ssh root@YOUR_SERVER_IP 'systemctl status neurocards-bot'

# Смотрим логи
ssh root@YOUR_SERVER_IP 'journalctl -u neurocards-bot -n 50'
```

### Генерация не работает

```bash
# Проверяем worker
ssh root@YOUR_SERVER_IP 'systemctl status neurocards-worker@1'

# Смотрим логи
ssh root@YOUR_SERVER_IP 'journalctl -u neurocards-worker@1 -n 50'
```

### База данных

```bash
# Подключаемся к PostgreSQL
ssh root@YOUR_SERVER_IP
sudo -u postgres psql -d neurocards

# Проверяем пользователей
SELECT * FROM users ORDER BY created_at DESC LIMIT 5;

# Проверяем задания
SELECT id, status, template_type, created_at FROM jobs ORDER BY created_at DESC LIMIT 10;
```

---

## 🎁 Бонусы

### Подключаем домен (опционально)

1. Покупаем домен (например, на Namecheap)
2. В DNS записях добавляем A-запись: `bot.yourdomain.com → YOUR_SERVER_IP`
3. Подключаемся к серверу:

```bash
ssh root@YOUR_SERVER_IP

# Устанавливаем SSL сертификат
systemctl stop nginx
certbot certonly --standalone -d bot.yourdomain.com
systemctl start nginx

# Обновляем .env
nano /home/botuser/neurocards-bot/.env
# Меняем WEBHOOK_URL на https://bot.yourdomain.com/webhook

# Перезапускаем бота
systemctl restart neurocards-bot
```

4. Обновляем webhook в Telegram:
```bash
curl -X POST "https://api.telegram.org/botBOT_TOKEN/setWebhook" \
  -d "url=https://bot.yourdomain.com/webhook"
```

### Настраиваем алерты в Telegram

Получайте уведомления если сервер упал:

```bash
ssh root@YOUR_SERVER_IP

# Создаем скрипт мониторинга
cat > /home/botuser/health_check.sh << 'EOF'
#!/bin/bash

TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID="YOUR_ADMIN_CHAT_ID"  # Ваш Telegram ID

send_alert() {
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=⚠️ ALERT: $1" > /dev/null
}

# Проверяем сервисы
systemctl is-active --quiet neurocards-bot || send_alert "Bot service is down!"
systemctl is-active --quiet neurocards-worker@1 || send_alert "Worker service is down!"

# Проверяем диск
DISK_USAGE=$(df -h / | awk 'NR==2{print +$5}')
if [ $DISK_USAGE -gt 90 ]; then
    send_alert "Disk usage is ${DISK_USAGE}%"
fi
EOF

chmod +x /home/botuser/health_check.sh

# Добавляем в crontab (проверка каждые 5 минут)
(crontab -l 2>/dev/null; echo "*/5 * * * * /home/botuser/health_check.sh") | crontab -
```

---

## 💰 Стоимость

| Позиция | Цена |
|---------|------|
| VPS Hetzner CPX21 | €4.51/мес (~$5) |
| KIE.AI (видео) | Pay-as-you-go |
| OpenAI (промпты) | ~$0.50/1000 генераций |
| **ИТОГО** | **~$5-7/мес** |

**Сравнение с Render + Supabase:** $25-30/мес

**Экономия: $20-25/мес ($240-300/год)** 🎉

---

## 📚 Полезные ссылки

- [SELF_HOSTING.md](SELF_HOSTING.md) - подробная инструкция по self-hosting
- [DEPLOYMENT.md](DEPLOYMENT.md) - деплой на Render.com
- [PARALLEL_WORKERS.md](PARALLEL_WORKERS.md) - масштабирование worker'ов
- [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md) - миграция БД

---

**Вопросы? Создавайте Issue на GitHub!** 🚀
