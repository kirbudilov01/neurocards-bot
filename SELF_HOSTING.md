# 🏠 Self-Hosting Guide: Полный переезд на свой VPS

Полная миграция с Render + Supabase на собственный сервер.

## 📋 Что получим

- ✅ Полный контроль над инфраструктурой
- ✅ Снижение затрат (VPS ~$5-10/мес вместо $25+/мес)
- ✅ Не зависим от лимитов Supabase/Render
- ✅ Быстрее работа (все на одном сервере)
- ✅ Можем масштабировать как угодно

---

## 🖥️ Выбор VPS

### Рекомендации:

**Минимальные требования:**
- 2 CPU cores
- 4 GB RAM
- 50 GB SSD
- Ubuntu 22.04 / 24.04 LTS

**Провайдеры (по возрастанию цены):**

1. **Hetzner** (Германия) - от €4.51/мес (~$5)
   - CPX21: 3 vCPU, 4 GB RAM, 80 GB SSD
   - Отличная цена/качество
   - https://www.hetzner.com/cloud

2. **DigitalOcean** (США/Европа) - от $6/мес
   - Droplet Basic: 2 vCPU, 2 GB RAM, 50 GB SSD
   - Простая панель управления
   - https://www.digitalocean.com

3. **Vultr** (США/Европа/Азия) - от $6/мес
   - High Performance: 2 vCPU, 4 GB RAM, 80 GB SSD
   - Много локаций
   - https://www.vultr.com

4. **Linode (Akamai)** (США/Европа/Азия) - от $12/мес
   - Shared CPU: 2 vCPU, 4 GB RAM, 80 GB SSD
   - Надежность
   - https://www.linode.com

**Рекомендация:** Hetzner CPX21 - лучший баланс цены и производительности.

---

## 📦 Установка на сервер

### 1. Подключение к серверу

```bash
# Подключаемся по SSH (заменить YOUR_SERVER_IP)
ssh root@YOUR_SERVER_IP
```

### 2. Базовая настройка безопасности

```bash
# Обновляем систему
apt update && apt upgrade -y

# Устанавливаем firewall
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw allow 8443/tcp    # Telegram webhook
ufw enable

# Создаем пользователя для приложения
adduser botuser --disabled-password --gecos ""
usermod -aG sudo botuser

# Настраиваем автоматические обновления безопасности
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

### 3. Установка PostgreSQL

```bash
# Устанавливаем PostgreSQL 15
apt install -y postgresql postgresql-contrib

# Создаем базу данных
sudo -u postgres psql << EOF
CREATE DATABASE neurocards;
CREATE USER botuser WITH PASSWORD 'STRONG_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON DATABASE neurocards TO botuser;
\c neurocards
GRANT ALL ON SCHEMA public TO botuser;
EOF

# Проверяем подключение
sudo -u postgres psql -d neurocards -c "SELECT version();"
```

### 4. Загрузка схемы базы данных

```bash
# Копируем schema.sql на сервер (выполнить с локальной машины)
scp /workspaces/neurocards-bot/supabase/schema.sql root@YOUR_SERVER_IP:/tmp/

# На сервере применяем схему
sudo -u postgres psql -d neurocards -f /tmp/schema.sql
```

### 5. Миграция данных из Supabase (если есть пользователи)

```bash
# В Supabase Dashboard → SQL Editor экспортируем данные:
COPY (SELECT * FROM users) TO STDOUT WITH CSV HEADER;
COPY (SELECT * FROM jobs) TO STDOUT WITH CSV HEADER;

# Сохраняем в файлы users.csv, jobs.csv
# Копируем на сервер
scp users.csv jobs.csv root@YOUR_SERVER_IP:/tmp/

# Импортируем на сервере
sudo -u postgres psql -d neurocards << EOF
\COPY users FROM '/tmp/users.csv' CSV HEADER;
\COPY jobs FROM '/tmp/jobs.csv' CSV HEADER;
EOF
```

### 6. Установка Python и зависимостей

```bash
# Устанавливаем Python 3.11+
apt install -y python3.11 python3.11-venv python3-pip git

# Клонируем репозиторий
su - botuser
cd ~
git clone https://github.com/YOUR_USERNAME/neurocards-bot.git
cd neurocards-bot

# Создаем виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install --upgrade pip
pip install -r requirements.txt

# Устанавливаем дополнительно asyncpg (если не в requirements.txt)
pip install asyncpg
```

### 7. Настройка переменных окружения

```bash
# Создаем .env файл
cat > /home/botuser/neurocards-bot/.env << 'EOF'
# Telegram Bot
BOT_TOKEN=your_bot_token_here
WEBHOOK_URL=https://YOUR_DOMAIN_OR_IP:8443/webhook

# PostgreSQL (локальная база)
DATABASE_URL=postgresql://botuser:STRONG_PASSWORD_HERE@localhost:5432/neurocards

# Supabase (только для Storage, пока не мигрировали файлы)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_key_here

# API Keys
KIE_API_KEY=your_kie_api_key
OPENAI_API_KEY=your_openai_api_key

# Environment
ENVIRONMENT=production
EOF

chmod 600 /home/botuser/neurocards-bot/.env
```

---

## 🔄 Настройка systemd сервисов

### 1. Сервис для бота (webhook)

```bash
# Создаем systemd unit файл
sudo tee /etc/systemd/system/neurocards-bot.service << 'EOF'
[Unit]
Description=Neurocards Telegram Bot
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/neurocards-bot
Environment="PATH=/home/botuser/neurocards-bot/venv/bin"
EnvironmentFile=/home/botuser/neurocards-bot/.env
ExecStart=/home/botuser/neurocards-bot/venv/bin/python -m app.main
Restart=always
RestartSec=10

# Логирование
StandardOutput=journal
StandardError=journal
SyslogIdentifier=neurocards-bot

[Install]
WantedBy=multi-user.target
EOF

# Включаем и запускаем
sudo systemctl daemon-reload
sudo systemctl enable neurocards-bot
sudo systemctl start neurocards-bot
sudo systemctl status neurocards-bot

# Смотрим логи
sudo journalctl -u neurocards-bot -f
```

### 2. Сервис для worker

```bash
# Создаем systemd unit файл
sudo tee /etc/systemd/system/neurocards-worker.service << 'EOF'
[Unit]
Description=Neurocards Video Generation Worker
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/neurocards-bot
Environment="PATH=/home/botuser/neurocards-bot/venv/bin"
EnvironmentFile=/home/botuser/neurocards-bot/.env
ExecStart=/home/botuser/neurocards-bot/venv/bin/python -m worker.worker
Restart=always
RestartSec=10

# Логирование
StandardOutput=journal
StandardError=journal
SyslogIdentifier=neurocards-worker

[Install]
WantedBy=multi-user.target
EOF

# Включаем и запускаем
sudo systemctl daemon-reload
sudo systemctl enable neurocards-worker
sudo systemctl start neurocards-worker
sudo systemctl status neurocards-worker

# Смотрим логи
sudo journalctl -u neurocards-worker -f
```

### 3. Запуск нескольких worker'ов (для масштабирования)

```bash
# Создаем шаблон сервиса
sudo tee /etc/systemd/system/neurocards-worker@.service << 'EOF'
[Unit]
Description=Neurocards Video Generation Worker #%i
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/neurocards-bot
Environment="PATH=/home/botuser/neurocards-bot/venv/bin"
Environment="WORKER_ID=%i"
EnvironmentFile=/home/botuser/neurocards-bot/.env
ExecStart=/home/botuser/neurocards-bot/venv/bin/python -m worker.worker
Restart=always
RestartSec=10

StandardOutput=journal
StandardError=journal
SyslogIdentifier=neurocards-worker-%i

[Install]
WantedBy=multi-user.target
EOF

# Запускаем 3 worker'а параллельно
sudo systemctl enable neurocards-worker@{1..3}
sudo systemctl start neurocards-worker@{1..3}

# Проверяем статус
sudo systemctl status neurocards-worker@*
```

---

## 🌐 Настройка Nginx + SSL

### 1. Установка Nginx

```bash
apt install -y nginx certbot python3-certbot-nginx
```

### 2. Конфигурация для бота

```bash
# Создаем конфиг
sudo tee /etc/nginx/sites-available/neurocards-bot << 'EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    # Редирект на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name YOUR_DOMAIN_OR_IP;

    # SSL сертификаты (настроим через certbot)
    ssl_certificate /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem;

    # Webhook endpoint для Telegram
    location /webhook {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check
    location /healthz {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }
}
EOF

# Активируем конфиг
sudo ln -s /etc/nginx/sites-available/neurocards-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. Получение SSL сертификата (если есть домен)

```bash
# Останавливаем nginx на время получения сертификата
sudo systemctl stop nginx

# Получаем сертификат
sudo certbot certonly --standalone -d YOUR_DOMAIN

# Запускаем nginx обратно
sudo systemctl start nginx

# Настраиваем автообновление
sudo systemctl enable certbot.timer
```

### 4. Настройка без домена (self-signed сертификат)

```bash
# Генерируем self-signed сертификат
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/selfsigned.key \
  -out /etc/nginx/ssl/selfsigned.crt \
  -subj "/C=RU/ST=Moscow/L=Moscow/O=Neurocards/CN=YOUR_SERVER_IP"

# Обновляем конфиг nginx
sudo sed -i 's|/etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem|/etc/nginx/ssl/selfsigned.crt|' /etc/nginx/sites-available/neurocards-bot
sudo sed -i 's|/etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem|/etc/nginx/ssl/selfsigned.key|' /etc/nginx/sites-available/neurocards-bot

sudo nginx -t && sudo systemctl reload nginx
```

---

## 📁 Миграция файлового хранилища

### Вариант 1: MinIO (S3-совместимое хранилище)

```bash
# Устанавливаем MinIO
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/

# Создаем директории
sudo mkdir -p /mnt/minio/neurocards
sudo chown -R botuser:botuser /mnt/minio

# Создаем systemd сервис
sudo tee /etc/systemd/system/minio.service << 'EOF'
[Unit]
Description=MinIO Object Storage
After=network.target

[Service]
Type=simple
User=botuser
Environment="MINIO_ROOT_USER=admin"
Environment="MINIO_ROOT_PASSWORD=STRONG_PASSWORD_HERE"
ExecStart=/usr/local/bin/minio server /mnt/minio --console-address :9001
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Запускаем
sudo systemctl enable minio
sudo systemctl start minio

# Открываем порты (только для локального доступа)
ufw allow from 127.0.0.1 to any port 9000
ufw allow from 127.0.0.1 to any port 9001

# Устанавливаем клиент
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

# Настраиваем alias
mc alias set local http://localhost:9000 admin STRONG_PASSWORD_HERE

# Создаем buckets
mc mb local/inputs
mc mb local/outputs

# Устанавливаем публичный доступ для outputs
mc anonymous set download local/outputs
```

**Обновляем код для MinIO:**

```python
# В app/config.py и worker/config.py добавляем:
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "STRONG_PASSWORD_HERE")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Устанавливаем библиотеку
pip install minio
```

### Вариант 2: Локальное хранилище (проще)

```bash
# Создаем директории
sudo mkdir -p /var/neurocards/storage/{inputs,outputs}
sudo chown -R botuser:botuser /var/neurocards

# В .env добавляем
echo "STORAGE_TYPE=local" >> /home/botuser/neurocards-bot/.env
echo "STORAGE_PATH=/var/neurocards/storage" >> /home/botuser/neurocards-bot/.env

# Настраиваем Nginx для раздачи outputs
sudo tee -a /etc/nginx/sites-available/neurocards-bot << 'EOF'

    # Статические файлы (готовые видео)
    location /outputs/ {
        alias /var/neurocards/storage/outputs/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
EOF

sudo nginx -t && sudo systemctl reload nginx
```

**Обновляем код для локального хранилища:**

Создаем [app/services/local_storage.py](app/services/local_storage.py):

```python
import os
import aiofiles
from pathlib import Path
from typing import Optional

class LocalStorage:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.inputs_path = self.base_path / "inputs"
        self.outputs_path = self.base_path / "outputs"
        
        # Создаем директории
        self.inputs_path.mkdir(parents=True, exist_ok=True)
        self.outputs_path.mkdir(parents=True, exist_ok=True)
    
    async def upload_file(self, bucket: str, filename: str, file_data: bytes) -> str:
        """Загружает файл и возвращает путь"""
        bucket_path = self.base_path / bucket
        file_path = bucket_path / filename
        
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)
        
        return f"/{bucket}/{filename}"
    
    async def get_public_url(self, bucket: str, filename: str) -> str:
        """Возвращает публичный URL для файла"""
        base_url = os.getenv("BASE_URL", "https://YOUR_DOMAIN")
        return f"{base_url}/{bucket}/{filename}"
    
    async def download_file(self, bucket: str, filename: str) -> bytes:
        """Скачивает файл"""
        file_path = self.base_path / bucket / filename
        
        async with aiofiles.open(file_path, 'rb') as f:
            return await f.read()
```

---

## 🔄 Обновление кода

Создаем файл для автоматического определения типа хранилища:

```bash
cat > /home/botuser/neurocards-bot/app/services/storage_factory.py << 'EOF'
import os
from app.services.storage import SupabaseStorage
from app.services.local_storage import LocalStorage

def get_storage():
    """Фабрика для получения нужного типа хранилища"""
    storage_type = os.getenv("STORAGE_TYPE", "supabase")
    
    if storage_type == "local":
        storage_path = os.getenv("STORAGE_PATH", "/var/neurocards/storage")
        return LocalStorage(storage_path)
    else:
        # Supabase по умолчанию (для обратной совместимости)
        from app.services.storage import storage
        return storage
EOF
```

---

## 🚀 Запуск и проверка

### 1. Проверка всех сервисов

```bash
# Проверяем статус
sudo systemctl status postgresql
sudo systemctl status neurocards-bot
sudo systemctl status neurocards-worker
sudo systemctl status nginx

# Смотрим логи
sudo journalctl -u neurocards-bot -n 50 --no-pager
sudo journalctl -u neurocards-worker -n 50 --no-pager
```

### 2. Настройка Telegram webhook

```bash
# Устанавливаем webhook (заменить BOT_TOKEN и YOUR_DOMAIN)
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://YOUR_DOMAIN/webhook\"}"

# Проверяем webhook
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

### 3. Тестирование

```bash
# Отправляем тестовое сообщение боту в Telegram
# /start

# Проверяем логи бота
sudo journalctl -u neurocards-bot -f

# Проверяем базу данных
sudo -u postgres psql -d neurocards -c "SELECT * FROM users ORDER BY created_at DESC LIMIT 5;"
```

---

## 📊 Мониторинг

### 1. Установка Netdata (опционально)

```bash
# Устанавливаем Netdata для мониторинга
bash <(curl -Ss https://my-netdata.io/kickstart.sh)

# Открываем доступ
ufw allow from YOUR_IP to any port 19999

# Открываем в браузере
# http://YOUR_SERVER_IP:19999
```

### 2. Простой скрипт мониторинга

```bash
cat > /home/botuser/monitor.sh << 'EOF'
#!/bin/bash

echo "=== Neurocards Bot Status ==="
echo ""

echo "📊 Services:"
systemctl is-active --quiet neurocards-bot && echo "✅ Bot: Running" || echo "❌ Bot: Stopped"
systemctl is-active --quiet neurocards-worker && echo "✅ Worker: Running" || echo "❌ Worker: Stopped"
systemctl is-active --quiet postgresql && echo "✅ PostgreSQL: Running" || echo "❌ PostgreSQL: Stopped"
systemctl is-active --quiet nginx && echo "✅ Nginx: Running" || echo "❌ Nginx: Stopped"

echo ""
echo "💾 Database:"
sudo -u postgres psql -d neurocards -t -c "SELECT COUNT(*) FROM users;" | xargs echo "Users:"
sudo -u postgres psql -d neurocards -t -c "SELECT COUNT(*) FROM jobs WHERE status = 'queued';" | xargs echo "Queued jobs:"
sudo -u postgres psql -d neurocards -t -c "SELECT COUNT(*) FROM jobs WHERE status = 'processing';" | xargs echo "Processing:"

echo ""
echo "💻 System:"
echo "CPU: $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}')"
echo "RAM: $(free -m | awk 'NR==2{printf "%.0f%%", $3*100/$2 }')"
echo "Disk: $(df -h / | awk 'NR==2{print $5}')"
EOF

chmod +x /home/botuser/monitor.sh

# Запускаем
/home/botuser/monitor.sh
```

### 3. Настройка алертов (Telegram)

```bash
cat > /home/botuser/health_check.sh << 'EOF'
#!/bin/bash

TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID="YOUR_ADMIN_CHAT_ID"

send_alert() {
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=⚠️ ALERT: $1" > /dev/null
}

# Проверяем сервисы
systemctl is-active --quiet neurocards-bot || send_alert "Bot service is down!"
systemctl is-active --quiet neurocards-worker || send_alert "Worker service is down!"
systemctl is-active --quiet postgresql || send_alert "PostgreSQL is down!"

# Проверяем место на диске
DISK_USAGE=$(df -h / | awk 'NR==2{print +$5}')
if [ $DISK_USAGE -gt 90 ]; then
    send_alert "Disk usage is ${DISK_USAGE}%"
fi
EOF

chmod +x /home/botuser/health_check.sh

# Добавляем в crontab (каждые 5 минут)
(crontab -l 2>/dev/null; echo "*/5 * * * * /home/botuser/health_check.sh") | crontab -
```

---

## 🔄 Автоматические обновления

```bash
cat > /home/botuser/update.sh << 'EOF'
#!/bin/bash

cd /home/botuser/neurocards-bot

# Получаем обновления
git pull origin main

# Обновляем зависимости
source venv/bin/activate
pip install -r requirements.txt

# Перезапускаем сервисы
sudo systemctl restart neurocards-bot
sudo systemctl restart neurocards-worker

echo "✅ Update completed!"
EOF

chmod +x /home/botuser/update.sh

# Для обновления просто запускаем:
# /home/botuser/update.sh
```

---

## 💰 Сравнение затрат

| Сервис | Render + Supabase | Self-Hosted (Hetzner) |
|--------|-------------------|------------------------|
| VPS | - | €4.51/мес (~$5) |
| PostgreSQL | $25/мес | Включено |
| Storage | $0.021/GB | ~$0.10/GB (SSD) |
| Bandwidth | Unlimited | 20 TB/мес |
| **ИТОГО** | **~$25-30/мес** | **~$5-7/мес** |

**Экономия: ~$20-25/мес ($240-300/год)**

---

## ✅ Чеклист миграции

### Подготовка:
- [ ] Выбрать и создать VPS (Hetzner/DigitalOcean/Vultr)
- [ ] Настроить firewall и базовую безопасность
- [ ] Установить PostgreSQL и загрузить схему
- [ ] Экспортировать данные из Supabase (users, jobs)

### Установка:
- [ ] Склонировать репозиторий на сервер
- [ ] Установить Python зависимости
- [ ] Настроить .env файл
- [ ] Создать systemd сервисы (bot + worker)
- [ ] Настроить Nginx + SSL

### Хранилище:
- [ ] Выбрать вариант (MinIO или локальное)
- [ ] Настроить раздачу файлов через Nginx
- [ ] Обновить код для работы с новым хранилищем
- [ ] Мигрировать существующие файлы из Supabase Storage

### Запуск:
- [ ] Запустить все сервисы
- [ ] Настроить Telegram webhook
- [ ] Протестировать /start и генерацию
- [ ] Настроить мониторинг

### Финал:
- [ ] Удалить Render services
- [ ] Удалить Supabase проект
- [ ] Настроить бэкапы базы данных

---

## 🛡️ Бэкапы

```bash
# Создаем скрипт для бэкапа базы данных
cat > /home/botuser/backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/home/botuser/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Бэкап базы данных
sudo -u postgres pg_dump neurocards | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Бэкап файлов (если локальное хранилище)
tar -czf $BACKUP_DIR/storage_$DATE.tar.gz /var/neurocards/storage

# Удаляем старые бэкапы (старше 7 дней)
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "✅ Backup completed: $DATE"
EOF

chmod +x /home/botuser/backup.sh

# Добавляем в crontab (каждый день в 3:00)
(crontab -l 2>/dev/null; echo "0 3 * * * /home/botuser/backup.sh") | crontab -
```

---

## 🎯 Результат

После миграции получаем:

✅ **Полный контроль** - все на своем сервере  
✅ **Экономия $20-25/мес** - VPS дешевле managed сервисов  
✅ **Быстрее** - база и бот на одном сервере  
✅ **Масштабируемо** - запускаем сколько угодно worker'ов  
✅ **Независимость** - не зависим от лимитов Supabase/Render  

Вопросы? Пиши!
