#!/bin/sh
# Entrypoint для worker (database polling mode)

echo "🚀 Starting neurocards worker..."

# Инициализация storage директорий
STORAGE_BASE_PATH=${STORAGE_BASE_PATH:-/app/storage}
echo "📁 Initializing storage at $STORAGE_BASE_PATH..."
mkdir -p "$STORAGE_BASE_PATH/inputs" "$STORAGE_BASE_PATH/outputs" "$STORAGE_BASE_PATH/temp"
chmod 755 "$STORAGE_BASE_PATH" "$STORAGE_BASE_PATH/inputs" "$STORAGE_BASE_PATH/outputs" "$STORAGE_BASE_PATH/temp" 2>/dev/null || true
echo "✅ Storage initialized"

# Worker uses database polling (fetch_next_queued_job), not RQ
echo "📡 Starting worker with database polling mode..."
exec python worker/worker.py
