#!/bin/bash

# 📦 Бэкап базы данных и файлов с VPS
# Использование: ./scripts/backup_vps.sh YOUR_SERVER_IP [local_backup_dir]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo -e "${RED}❌ Ошибка: не указан IP сервера${NC}"
    echo "Использование: $0 YOUR_SERVER_IP [local_backup_dir]"
    exit 1
fi

SERVER_IP=$1
LOCAL_BACKUP_DIR=${2:-./backups}
DATE=$(date +%Y%m%d_%H%M%S)

echo -e "${GREEN}💾 Создание бэкапа с ${SERVER_IP}${NC}"
echo ""

# Создаем локальную директорию для бэкапов
mkdir -p ${LOCAL_BACKUP_DIR}

# 1. Бэкап базы данных
echo -e "${YELLOW}📊 Создание дампа базы данных...${NC}"
ssh root@${SERVER_IP} "sudo -u postgres pg_dump neurocards | gzip" > ${LOCAL_BACKUP_DIR}/db_${DATE}.sql.gz
echo -e "${GREEN}✅ База данных: ${LOCAL_BACKUP_DIR}/db_${DATE}.sql.gz${NC}"

# 2. Бэкап файлов хранилища (если используется локальное)
echo ""
echo -e "${YELLOW}📁 Создание архива файлов...${NC}"
ssh root@${SERVER_IP} "tar -czf - /var/neurocards/storage 2>/dev/null" > ${LOCAL_BACKUP_DIR}/storage_${DATE}.tar.gz || true
echo -e "${GREEN}✅ Файлы: ${LOCAL_BACKUP_DIR}/storage_${DATE}.tar.gz${NC}"

# 3. Бэкап конфигурации
echo ""
echo -e "${YELLOW}⚙️  Сохранение конфигурации...${NC}"
ssh root@${SERVER_IP} "cat /home/botuser/neurocards-bot/.env" > ${LOCAL_BACKUP_DIR}/env_${DATE}.txt
echo -e "${GREEN}✅ Конфигурация: ${LOCAL_BACKUP_DIR}/env_${DATE}.txt${NC}"

# Размеры
echo ""
echo -e "${GREEN}📦 Размеры бэкапов:${NC}"
ls -lh ${LOCAL_BACKUP_DIR}/*_${DATE}* | awk '{print "  " $9 ": " $5}'

echo ""
echo -e "${GREEN}✅ Бэкап завершен!${NC}"
echo -e "${YELLOW}💡 Для восстановления используйте: ./scripts/restore_vps.sh${NC}"
