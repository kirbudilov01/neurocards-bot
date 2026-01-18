#!/bin/bash

# 🔄 Скрипт для обновления бота на VPS
# Использование: ./scripts/update_vps.sh YOUR_SERVER_IP

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo -e "${RED}❌ Ошибка: не указан IP сервера${NC}"
    echo "Использование: $0 YOUR_SERVER_IP"
    exit 1
fi

SERVER_IP=$1
SERVER_USER="botuser"

echo -e "${GREEN}🔄 Обновление бота на ${SERVER_IP}${NC}"
echo ""

# Обновляем код
echo -e "${YELLOW}📥 Получаем последние изменения...${NC}"
ssh ${SERVER_USER}@${SERVER_IP} << 'ENDSSH'
    cd ~/neurocards-bot
    git pull origin main
    
    # Активируем виртуальное окружение
    source venv/bin/activate
    
    # Обновляем зависимости
    pip install --upgrade pip
    pip install -r requirements.txt
ENDSSH

echo ""

# Перезапускаем сервисы
echo -e "${YELLOW}🔄 Перезапускаем сервисы...${NC}"
ssh root@${SERVER_IP} << 'ENDSSH'
    systemctl restart neurocards-bot
    systemctl restart 'neurocards-worker@*'
    
    # Ждем 3 секунды
    sleep 3
    
    # Проверяем статус
    echo ""
    echo "📊 Статус после обновления:"
    systemctl is-active --quiet neurocards-bot && echo "✅ Bot: Running" || echo "❌ Bot: Failed"
    systemctl is-active --quiet 'neurocards-worker@*' && echo "✅ Workers: Running" || echo "❌ Workers: Failed"
ENDSSH

echo ""
echo -e "${GREEN}✅ Обновление завершено!${NC}"
echo ""
echo -e "${YELLOW}📝 Проверьте логи:${NC}"
echo "  ssh ${SERVER_USER}@${SERVER_IP} 'sudo journalctl -u neurocards-bot -n 50'"
echo "  ssh ${SERVER_USER}@${SERVER_IP} 'sudo journalctl -u neurocards-worker@1 -n 50'"
