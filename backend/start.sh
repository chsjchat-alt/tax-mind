#!/bin/bash
set -e

# ══════════════════════════════════════════════════════════════════
#  蒙牛全产业链 AI 内生合规决策大脑 — 启动脚本（兼容 Docker Compose 与 Railway 单容器）
#  1) PostgreSQL 模式：等待 DB 就绪 → alembic 迁移 → 导入种子数据
#  2) SQLite 模式（开发）：跳过等待/迁移（应用启动时自动建表）
# ══════════════════════════════════════════════════════════════════

if echo "${DATABASE_URL}" | grep -q "postgresql"; then
    echo "等待 PostgreSQL 就绪..."
    python - <<'PY'
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def normalize_url(url: str) -> str:
    """与 app/config.py 保持一致：postgresql:// → postgresql+asyncpg://
    否则 SQLAlchemy 对同步前缀默认加载 psycopg2 方言 → ModuleNotFoundError"""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def wait_for_db(url: str, max_attempts: int = 60) -> None:
    url = normalize_url(url)
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                print("PostgreSQL 已就绪")
                return
            except Exception as exc:  # noqa: BLE001 - 等待期异常需逐一吞掉重试
                print(f"  等待中 ({attempt}/{max_attempts}): {type(exc).__name__}")
                await asyncio.sleep(1)
        print("ERROR: 数据库连接超时", file=sys.stderr)
        sys.exit(1)
    finally:
        await engine.dispose()

asyncio.run(wait_for_db(os.environ["DATABASE_URL"]))
PY

    echo "同步数据库表结构（模型驱动 create_all，幂等）..."
    cd /app
    python - <<'PY'
import asyncio

from sqlalchemy import inspect

import app.models  # noqa: F401 注册全部模型
from app.database import Base, engine


def _schema_fresh(sync_conn) -> bool:
    """判断现有 schema 是否与 ORM 模型同步：
    - 全新数据库（无 enterprises 表）→ 视为同步
    - 旧 alembic 迁移残留表（uuid 主键、缺 industry_benchmark_id 等新列）→ 不同步"""
    insp = inspect(sync_conn)
    if "enterprises" not in insp.get_table_names():
        return True
    cols = {c["name"]: str(c["type"]) for c in insp.get_columns("enterprises")}
    return cols.get("id") == "VARCHAR(36)" and "industry_benchmark_id" in cols


async def main() -> None:
    async with engine.connect() as conn:
        fresh = await conn.run_sync(_schema_fresh)
    if not fresh:
        # 旧 alembic 迁移残留的过期 schema（uuid 主键等）与模型不兼容，
        # 必须先重建，否则 create_all 会因 FK 类型不匹配失败。
        print("检测到旧迁移残留 schema，重建全部表...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(main())
PY

    echo "幂等补齐生产 schema（补列/建表/种子，覆盖 create_all 无法处理的存量库漂移）..."
    python scripts/migrate_schema.py

    echo "导入种子数据（幂等）..."
    python seed_multi_tenant.py
else
    echo "使用 SQLite 模式，跳过 PostgreSQL 等待、迁移与种子导入..."
fi

echo "启动 FastAPI 服务..."
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}"
