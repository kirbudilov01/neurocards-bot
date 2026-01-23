#!/bin/bash

# 🚀 Автоматический деплой на VPS
# Использование: ./scripts/deploy_to_vps.sh YOUR_SERVER_IP

set -e  # Выходим при любой ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$1" ]; then
    echo -e "${RED}❌ Ошибка: не указан IP сервера${NC}"
    echo "Использование: $0 YOUR_SERVER_IP"
    exit 1
fi

SERVER_IP=$1
SERVER_USER="root"

echo -e "${GREEN}🚀 Начинаем деплой на ${SERVER_IP}${NC}"
echo ""

# 1. Подключение и базовая настройка
echo -e "${YELLOW}📦 Шаг 1: Базовая настройка сервера${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    set -e
    
    # Обновляем систему
    apt update && apt upgrade -y
    
    # Устанавливаем необходимые пакеты
    apt install -y python3 python3-venv python3-pip git postgresql postgresql-contrib nginx ufw
    
    # Настраиваем firewall
    ufw --force enable
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 8443/tcp
    
    # Создаем пользователя для приложения (если не существует)
    if ! id -u botuser > /dev/null 2>&1; then
        adduser botuser --disabled-password --gecos ""
        usermod -aG sudo botuser
    fi
    
    echo "✅ Базовая настройка завершена"
ENDSSH

echo ""

# 2. Настройка PostgreSQL
echo -e "${YELLOW}💾 Шаг 2: Настройка PostgreSQL${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    set -e
    
    # Генерируем случайный пароль
    DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    
    # Создаем базу данных
    sudo -u postgres psql << EOF
\set ON_ERROR_STOP on

-- Создаем базу данных (если не существует)
SELECT 'CREATE DATABASE neurocards'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'neurocards')\gexec

-- Создаем пользователя (если не существует)
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'botuser') THEN
        CREATE USER botuser WITH PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;

-- Даем права
GRANT ALL PRIVILEGES ON DATABASE neurocards TO botuser;
\c neurocards
GRANT ALL ON SCHEMA public TO botuser;
GRANT ALL ON ALL TABLES IN SCHEMA public TO botuser;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO botuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO botuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO botuser;
EOF
    
    # Сохраняем пароль в файл
    echo "DB_PASSWORD=${DB_PASSWORD}" > /tmp/db_credentials.txt
    
    echo "✅ PostgreSQL настроен"
ENDSSH

# Получаем пароль БД
DB_PASSWORD=$(ssh ${SERVER_USER}@${SERVER_IP} "cat /tmp/db_credentials.txt | grep DB_PASSWORD | cut -d= -f2")

echo ""

# 3. Клонирование репозитория
echo -e "${YELLOW}📥 Шаг 3: Клонирование репозитория${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << ENDSSH
    set -e
    
    # Создаём директорию проекта
    mkdir -p /var/neurocards
    cd /var/neurocards
    
    # Удаляем старый репозиторий если есть
    rm -rf neurocards-bot
    
    # Клонируем репозиторий
    git clone https://github.com/kirbudilov01/neurocards-bot.git
    
    cd neurocards-bot
    
    # Создаем виртуальное окружение с Python 3
    python3 -m venv venv
    source venv/bin/activate
    
    # Обновляем pip
    pip install --upgrade pip
    
    # Устанавливаем зависимости
    pip install -r requirements.txt
    
    echo "✅ Репозиторий склонирован и зависимости установлены"
ENDSSH

echo ""

# 4. Загрузка схемы базы данных
echo -e "${YELLOW}📊 Шаг 4: Загрузка схемы базы данных${NC}"

# Копируем schema.sql на сервер
scp database/schema.sql ${SERVER_USER}@${SERVER_IP}:/tmp/schema.sql

ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    set -e
    
    # Применяем схему
    sudo -u postgres psql -d neurocards -f /tmp/schema.sql
    
    # Удаляем временный файл
    rm /tmp/schema.sql
    
    echo "✅ Схема базы данных загружена"
ENDSSH

echo ""

# 5. Настройка переменных окружения
echo -e "${YELLOW}⚙️  Шаг 5: Настройка переменных окружения${NC}"
echo ""
echo -e "${YELLOW}Необходимо ввести значения:${NC}"
read -p "BOT_TOKEN: " BOT_TOKEN
read -p "WEBHOOK_URL (https://YOUR_DOMAIN:8443/webhook): " WEBHOOK_URL
read -p "KIE_API_KEY: " KIE_API_KEY
read -p "OPENAI_API_KEY: " OPENAI_API_KEY

# Создаем .env файл на сервере
ssh ${SERVER_USER}@${SERVER_IP} << ENDSSH
    set -e
    
    cat > /home/botuser/neurocards-bot/.env << EOF
# Telegram Bot
BOT_TOKEN=${BOT_TOKEN}
WEBHOOK_URL=${WEBHOOK_URL}

# PostgreSQL
DATABASE_URL=postgresql://botuser:${DB_PASSWORD}@localhost:5432/neurocards

# API Keys
KIE_API_KEY=${KIE_API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY}

# Storage (локальное хранилище)
STORAGE_TYPE=local
STORAGE_PATH=/var/neurocards/storage
BASE_URL=${WEBHOOK_URL%%/webhook}

# Environment
ENVIRONMENT=production
EOF
    
    chmod 600 /home/botuser/neurocards-bot/.env
    chown botuser:botuser /home/botuser/neurocards-bot/.env
    
    # Создаем директории для хранилища
    mkdir -p /var/neurocards/storage/{inputs,outputs}
    chown -R botuser:botuser /var/neurocards
    
    echo "✅ Переменные окружения настроены"
ENDSSH

echo ""

# 6. Создание systemd сервисов
echo -e "${YELLOW}🔧 Шаг 6: Создание systemd сервисов${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    set -e
    
    # Сервис для бота
    cat > /etc/systemd/system/neurocards-bot.service << EOF
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

StandardOutput=journal
StandardError=journal
SyslogIdentifier=neurocards-bot

[Install]
WantedBy=multi-user.target
EOF
    
    # Сервис для worker (template для нескольких инстансов)
    cat > /etc/systemd/system/neurocards-worker@.service << EOF
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
    
    # Перезагружаем systemd
    systemctl daemon-reload
    
    echo "✅ Systemd сервисы созданы"
ENDSSH

echo ""

# 7. Настройка Nginx
echo -e "${YELLOW}🌐 Шаг 7: Настройка Nginx${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << ENDSSH
    set -e
    
    # Создаем конфиг Nginx
    cat > /etc/nginx/sites-available/neurocards-bot << EOF
server {
    listen 80 default_server;
    server_name _;

    # Health check
    location /healthz {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }

    # Webhook endpoint для Telegram
    location /webhook {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Статические файлы (готовые видео)
    location /outputs/ {
        alias /var/neurocards/storage/outputs/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
EOF
    
    # Активируем конфиг
    rm -f /etc/nginx/sites-enabled/default
    ln -sf /etc/nginx/sites-available/neurocards-bot /etc/nginx/sites-enabled/
    
    # Проверяем конфиг
    nginx -t
    
    # Перезагружаем Nginx
    systemctl reload nginx
    
    echo "✅ Nginx настроен"
ENDSSH

echo ""

# 8. Запуск сервисов
echo -e "${YELLOW}🚀 Шаг 8: Запуск сервисов${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    set -e
    
    # Включаем и запускаем бота
    systemctl enable neurocards-bot
    systemctl start neurocards-bot
    
    # Включаем и запускаем worker (1 инстанс)
    systemctl enable neurocards-worker@1
    systemctl start neurocards-worker@1
    
    # Ждем 3 секунды
    sleep 3
    
    # Проверяем статус
    echo ""
    echo "📊 Статус сервисов:"
    systemctl is-active --quiet neurocards-bot && echo "✅ Bot: Running" || echo "❌ Bot: Failed"
    systemctl is-active --quiet neurocards-worker@1 && echo "✅ Worker #1: Running" || echo "❌ Worker #1: Failed"
    systemctl is-active --quiet postgresql && echo "✅ PostgreSQL: Running" || echo "❌ PostgreSQL: Failed"
    systemctl is-active --quiet nginx && echo "✅ Nginx: Running" || echo "❌ Nginx: Failed"
ENDSSH

echo ""
echo -e "${GREEN}✅ Деплой завершен!${NC}"
echo ""
echo -e "${YELLOW}📝 Следующие шаги:${NC}"
echo ""
echo "1. Настройте Telegram webhook:"
echo "   curl -X POST \"https://api.telegram.org/bot${BOT_TOKEN}/setWebhook\" \\"
echo "     -d \"url=${WEBHOOK_URL}\""
echo ""
echo "2. Проверьте логи:"
echo "   ssh ${SERVER_USER}@${SERVER_IP} 'sudo journalctl -u neurocards-bot -f'"
echo ""
echo "3. Протестируйте бота в Telegram"
echo ""
echo "4. Для запуска дополнительных worker'ов:"
echo "   ssh ${SERVER_USER}@${SERVER_IP} 'sudo systemctl enable neurocards-worker@{2..3} && sudo systemctl start neurocards-worker@{2..3}'"
echo ""
echo -e "${GREEN}🎉 Готово!${NC}"
