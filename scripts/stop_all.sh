#!/bin/bash
# Скрипт для остановки всех сервисов

echo "⏹ Stopping all services..."

# Останавливаем бота
sudo systemctl stop neurocards-bot-webhook.service

# Останавливаем всех воркеров
for i in {1..10}; do
    sudo systemctl stop neurocards-worker@$i.service 2>/dev/null || true
done

echo "✅ All services stopped"
