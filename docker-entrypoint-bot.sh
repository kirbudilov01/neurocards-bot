#!/bin/sh
# Entrypoint для бота - создание директорий для storage

STORAGE_PATH="${STORAGE_BASE_PATH:-/app/storage}"

echo "📁 Setting up storage directories at $STORAGE_PATH"

# Создаем директории если их нет
mkdir -p "$STORAGE_PATH/inputs" "$STORAGE_PATH/outputs" || true

# Устанавливаем права доступа для текущего пользователя
chmod -R 755 "$STORAGE_PATH" 2>/dev/null || true

echo "✅ Storage directories ready"

# Запускаем основную команду
exec "$@"
