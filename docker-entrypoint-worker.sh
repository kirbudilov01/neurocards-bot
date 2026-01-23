#!/bin/sh
# Entrypoint для RQ worker

# Значения по умолчанию
REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}
WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-5}

echo "🚀 Starting RQ worker..."
echo "📡 Redis URL: $REDIS_URL"
echo "⚡ Concurrency: $WORKER_CONCURRENCY"

# Инициализация storage директорий
STORAGE_BASE_PATH=${STORAGE_BASE_PATH:-/app/storage}
echo "📁 Initializing storage at $STORAGE_BASE_PATH..."
mkdir -p "$STORAGE_BASE_PATH/inputs" "$STORAGE_BASE_PATH/outputs" "$STORAGE_BASE_PATH/temp"
chmod 755 "$STORAGE_BASE_PATH" "$STORAGE_BASE_PATH/inputs" "$STORAGE_BASE_PATH/outputs" "$STORAGE_BASE_PATH/temp" 2>/dev/null || true
echo "✅ Storage initialized"

# Генерируем уникальное имя воркера (PID + случайное число)
WORKER_NAME="worker-$(hostname)-$$-${RANDOM}"

# Запускаем RQ worker (без --burst для непрерывной работы)
# --job-monitoring-interval 30: проверка heartbeat каждые 30 секунд
# --worker-ttl 2400: worker живет до 2400 секунд без heartbeat
# --disable-default-exception-handler: отключаем pubsub для стабильности
# Timeout задачи 1800s (30 минут) передается через enqueue()
exec python -m rq.cli worker neurocards \
  --url "$REDIS_URL" \
  --name "$WORKER_NAME" \
  --worker-ttl 2400 \
  --job-monitoring-interval 30 \
  --disable-default-exception-handler \
  --verbose
