#!/bin/sh
# Entrypoint для RQ worker

# Значения по умолчанию
REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}
WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-5}

echo "🚀 Starting RQ worker..."
echo "📡 Redis URL: $REDIS_URL"
echo "⚡ Concurrency: $WORKER_CONCURRENCY"

# Запускаем RQ worker
exec rq worker neurocards \
  --url "$REDIS_URL" \
  --burst \
  --name "worker-$$" \
  --verbose
