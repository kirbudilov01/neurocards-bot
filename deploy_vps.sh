#!/bin/bash
# Скрипт для развертывания бота и воркеров на VPS

set -e

echo "🚀 Starting Neurocards Bot Deployment"

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Проверка .env
if [ ! -f .env ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo "Please create .env file with required variables"
    exit 1
fi

# Загружаем переменные окружения
export $(cat .env | grep -v '^#' | xargs)

# Проверка обязательных переменных
REQUIRED_VARS=("BOT_TOKEN" "KIE_API_KEY" "DATABASE_URL")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}❌ Required variable $var is not set in .env${NC}"
        exit 1
    fi
done

echo -e "${GREEN}✅ Environment variables loaded${NC}"

# Останавливаем существующие сервисы
echo -e "${YELLOW}⏹ Stopping existing services...${NC}"
sudo systemctl stop neurocards-bot-webhook.service 2>/dev/null || true
for i in {1..5}; do
    sudo systemctl stop neurocards-worker@$i.service 2>/dev/null || true
done

# Устанавливаем зависимости
echo -e "${YELLOW}📦 Installing dependencies...${NC}"
pip3 install -r requirements.txt

# Применяем миграции БД
echo -e "${YELLOW}🗄️ Running database migrations...${NC}"
python3 scripts/migrate_db.py

# Копируем systemd сервисы
echo -e "${YELLOW}📋 Copying systemd service files...${NC}"
sudo cp systemd/neurocards-bot-webhook.service /etc/systemd/system/
sudo cp systemd/neurocards-worker@.service /etc/systemd/system/

# Обновляем WorkingDirectory в сервисах
CURRENT_DIR=$(pwd)
sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$CURRENT_DIR|g" /etc/systemd/system/neurocards-bot-webhook.service
sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$CURRENT_DIR|g" /etc/systemd/system/neurocards-worker@.service

# Reload systemd
echo -e "${YELLOW}🔄 Reloading systemd...${NC}"
sudo systemctl daemon-reload

# Запускаем бота
echo -e "${YELLOW}🤖 Starting bot service...${NC}"
sudo systemctl enable neurocards-bot-webhook.service
sudo systemctl start neurocards-bot-webhook.service

# Ждем запуска бота
sleep 3

# Проверяем статус бота
if sudo systemctl is-active --quiet neurocards-bot-webhook.service; then
    echo -e "${GREEN}✅ Bot service started successfully${NC}"
else
    echo -e "${RED}❌ Bot service failed to start${NC}"
    sudo journalctl -u neurocards-bot-webhook.service -n 50 --no-pager
    exit 1
fi

# Запускаем воркеры
WORKER_COUNT=${WORKER_INSTANCES:-5}
echo -e "${YELLOW}⚙️ Starting $WORKER_COUNT workers...${NC}"

for i in $(seq 1 $WORKER_COUNT); do
    echo -e "${YELLOW}  Starting worker $i...${NC}"
    sudo systemctl enable neurocards-worker@$i.service
    sudo systemctl start neurocards-worker@$i.service
    sleep 1
done

# Проверяем статус воркеров
echo ""
echo -e "${GREEN}📊 Services status:${NC}"
echo ""
sudo systemctl status neurocards-bot-webhook.service --no-pager | head -5
echo ""
for i in $(seq 1 $WORKER_COUNT); do
    if sudo systemctl is-active --quiet neurocards-worker@$i.service; then
        echo -e "${GREEN}✅ Worker $i: running${NC}"
    else
        echo -e "${RED}❌ Worker $i: failed${NC}"
    fi
done

echo ""
echo -e "${GREEN}🎉 Deployment completed!${NC}"
echo ""
echo "Commands:"
echo "  View bot logs:    sudo journalctl -u neurocards-bot-webhook.service -f"
echo "  View worker logs: sudo journalctl -u neurocards-worker@1.service -f"
echo "  Stop all:         ./scripts/stop_all.sh"
echo "  Restart all:      ./scripts/restart_all.sh"
echo ""
