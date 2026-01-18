#!/bin/bash

# 📊 Мониторинг состояния бота на VPS
# Использование: ./scripts/monitor_vps.sh YOUR_SERVER_IP

if [ -z "$1" ]; then
    echo "❌ Ошибка: не указан IP сервера"
    echo "Использование: $0 YOUR_SERVER_IP"
    exit 1
fi

SERVER_IP=$1

ssh root@${SERVER_IP} << 'ENDSSH'
#!/bin/bash

echo "═══════════════════════════════════════════════"
echo "     🤖 Neurocards Bot - Мониторинг"
echo "═══════════════════════════════════════════════"
echo ""

# Сервисы
echo "📊 Статус сервисов:"
echo "─────────────────────────────────────────────"
systemctl is-active --quiet neurocards-bot && echo "✅ Bot:        Running" || echo "❌ Bot:        Stopped"
systemctl is-active --quiet 'neurocards-worker@*' && echo "✅ Workers:    Running ($(systemctl list-units 'neurocards-worker@*' --state=running --no-legend | wc -l) instances)" || echo "❌ Workers:    Stopped"
systemctl is-active --quiet postgresql && echo "✅ PostgreSQL: Running" || echo "❌ PostgreSQL: Stopped"
systemctl is-active --quiet nginx && echo "✅ Nginx:      Running" || echo "❌ Nginx:      Stopped"
echo ""

# База данных
echo "💾 База данных:"
echo "─────────────────────────────────────────────"
TOTAL_USERS=$(sudo -u postgres psql -d neurocards -t -A -c "SELECT COUNT(*) FROM users;")
TOTAL_JOBS=$(sudo -u postgres psql -d neurocards -t -A -c "SELECT COUNT(*) FROM jobs;")
QUEUED_JOBS=$(sudo -u postgres psql -d neurocards -t -A -c "SELECT COUNT(*) FROM jobs WHERE status = 'queued';")
PROCESSING_JOBS=$(sudo -u postgres psql -d neurocards -t -A -c "SELECT COUNT(*) FROM jobs WHERE status = 'processing';")
DONE_JOBS=$(sudo -u postgres psql -d neurocards -t -A -c "SELECT COUNT(*) FROM jobs WHERE status = 'done';")
FAILED_JOBS=$(sudo -u postgres psql -d neurocards -t -A -c "SELECT COUNT(*) FROM jobs WHERE status = 'failed';")

echo "👥 Пользователей:         $TOTAL_USERS"
echo "📦 Всего заданий:         $TOTAL_JOBS"
echo "⏳ В очереди:             $QUEUED_JOBS"
echo "⚙️  Обрабатывается:        $PROCESSING_JOBS"
echo "✅ Выполнено:             $DONE_JOBS"
echo "❌ Ошибок:                $FAILED_JOBS"
echo ""

# Последние 5 пользователей
echo "👤 Последние пользователи:"
echo "─────────────────────────────────────────────"
sudo -u postgres psql -d neurocards -t -c "SELECT tg_user_id, credits, created_at FROM users ORDER BY created_at DESC LIMIT 5;" | sed 's/^/ /'
echo ""

# Последние задания
echo "📋 Последние задания:"
echo "─────────────────────────────────────────────"
sudo -u postgres psql -d neurocards -t -c "SELECT id, status, template_type, created_at FROM jobs ORDER BY created_at DESC LIMIT 5;" | sed 's/^/ /'
echo ""

# Системные ресурсы
echo "💻 Системные ресурсы:"
echo "─────────────────────────────────────────────"
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{printf "%.1f%%", 100 - $1}')
RAM_USAGE=$(free -m | awk 'NR==2{printf "%.0f%%", $3*100/$2 }')
DISK_USAGE=$(df -h / | awk 'NR==2{print $5}')
LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}')

echo "🔥 CPU:     $CPU_USAGE"
echo "🧠 RAM:     $RAM_USAGE"
echo "💾 Disk:    $DISK_USAGE"
echo "📊 Load:   $LOAD_AVG"
echo ""

# Хранилище
echo "📁 Хранилище файлов:"
echo "─────────────────────────────────────────────"
if [ -d "/var/neurocards/storage" ]; then
    INPUT_FILES=$(find /var/neurocards/storage/inputs -type f 2>/dev/null | wc -l)
    OUTPUT_FILES=$(find /var/neurocards/storage/outputs -type f 2>/dev/null | wc -l)
    STORAGE_SIZE=$(du -sh /var/neurocards/storage 2>/dev/null | cut -f1)
    
    echo "📥 Входных файлов:   $INPUT_FILES"
    echo "📤 Готовых видео:    $OUTPUT_FILES"
    echo "💾 Размер:           $STORAGE_SIZE"
else
    echo "⚠️  Локальное хранилище не настроено"
fi
echo ""

# Последние логи
echo "📝 Последние записи в логах:"
echo "─────────────────────────────────────────────"
echo "Bot:"
journalctl -u neurocards-bot -n 3 --no-pager --output=short | sed 's/^/  /'
echo ""
echo "Worker:"
journalctl -u 'neurocards-worker@*' -n 3 --no-pager --output=short | sed 's/^/  /'
echo ""

echo "═══════════════════════════════════════════════"
echo "✅ Мониторинг завершен"
echo "═══════════════════════════════════════════════"
ENDSSH
