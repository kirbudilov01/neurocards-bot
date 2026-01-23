#!/bin/bash
# Скрипт для перезапуска всех сервисов

echo "🔄 Restarting all services..."

# Перезапускаем бота
sudo systemctl restart neurocards-bot-webhook.service

# Перезапускаем воркеров
WORKER_COUNT=${WORKER_INSTANCES:-5}
for i in $(seq 1 $WORKER_COUNT); do
    sudo systemctl restart neurocards-worker@$i.service
done

echo "✅ All services restarted"
echo ""
echo "Check status:"
echo "  Bot:     sudo systemctl status neurocards-bot-webhook.service"
echo "  Workers: sudo systemctl status neurocards-worker@*.service"
