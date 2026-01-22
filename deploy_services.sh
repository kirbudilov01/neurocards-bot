#!/bin/bash
set -e

echo "🚀 Deploying Neurocards Bot Services..."

# Проверка .env
if [ ! -f /var/neurocards/neurocards-bot/.env ]; then
    echo "❌ .env file not found!"
    exit 1
fi

# Останавливаем старые сервисы
echo "⏹️  Stopping old services..."
systemctl stop neurocards-bot 2>/dev/null || true
systemctl stop neurocards-worker 2>/dev/null || true
systemctl disable neurocards-bot 2>/dev/null || true
systemctl disable neurocards-worker 2>/dev/null || true

# Копируем новые unit файлы
echo "📋 Copying new service files..."
cp /var/neurocards/neurocards-bot/systemd/neurocards-bot-webhook.service /etc/systemd/system/
cp /var/neurocards/neurocards-bot/systemd/neurocards-worker@.service /etc/systemd/system/

# Reload systemd
echo "🔄 Reloading systemd..."
systemctl daemon-reload

# Запускаем бота (webhook)
echo "▶️  Starting bot webhook service..."
systemctl enable neurocards-bot-webhook
systemctl start neurocards-bot-webhook

# Запускаем 5 воркеров
echo "▶️  Starting 5 worker instances..."
for i in {1..5}; do
    systemctl enable neurocards-worker@$i
    systemctl start neurocards-worker@$i
    sleep 1
done

echo ""
echo "✅ Services deployed successfully!"
echo ""
echo "📊 Status:"
systemctl status neurocards-bot-webhook --no-pager || true
echo ""
for i in {1..5}; do
    echo "Worker $i:"
    systemctl status neurocards-worker@$i --no-pager | head -5 || true
    echo ""
done

echo "📝 Logs:"
echo "  Bot: tail -f /var/neurocards/neurocards-bot/bot.log"
echo "  Worker 1: tail -f /var/neurocards/neurocards-bot/worker-1.log"
echo "  All workers: tail -f /var/neurocards/neurocards-bot/worker-*.log"
