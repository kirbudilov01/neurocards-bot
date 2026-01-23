#!/bin/bash
# Скрипт для запуска RQ воркеров в Docker контейнере

# Количество воркеров (по умолчанию из env или 3)
WORKER_COUNT=${WORKER_REPLICAS:-3}

echo "🚀 Starting $WORKER_COUNT RQ workers..."

# Запускаем воркеры в фоне
for i in $(seq 1 $WORKER_COUNT); do
    rq worker neurocards --url "$REDIS_URL" --burst --name "worker-$i" &
    echo "✅ Worker $i started (PID: $!)"
done

# Ждем завершения всех воркеров
wait

echo "✅ All workers finished"
