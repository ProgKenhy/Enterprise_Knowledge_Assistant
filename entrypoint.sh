#!/bin/sh
set -e

# Небольшая задержка, чтобы Postgres гарантированно начал принимать DDL запросы
# (иногда healthcheck срабатывает на миллисекунды раньше, чем БД готова к созданию таблиц)
sleep 2

echo "🚀 Applying database migrations..."
alembic upgrade head

echo "✅ Migrations applied. Starting service..."
# exec заменяет процесс shell на процесс приложения. 
# Это критически важно для корректной обработки сигналов (например, при docker stop или Ctrl+C)
exec "$@"