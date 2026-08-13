#!/bin/bash
set -e

# 仅在 PostgreSQL 模式下等待数据库就绪
if echo "${DATABASE_URL}" | grep -q "postgresql"; then
    DB_HOST="${DB_HOST:-postgres}"
    DB_USER="${POSTGRES_USER:-taxmind}"
    echo "等待 PostgreSQL 就绪 (host=$DB_HOST, user=$DB_USER)..."
    while ! pg_isready -h "$DB_HOST" -U "$DB_USER" -q; do
        sleep 1
    done
    echo "PostgreSQL 已就绪"

    echo "运行数据库迁移..."
    cd /app
    alembic upgrade head || echo "跳过迁移（尚未创建迁移脚本）"
else
    echo "使用 SQLite 模式，跳过 PostgreSQL 等待和迁移..."
fi

echo "启动 FastAPI 服务..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
