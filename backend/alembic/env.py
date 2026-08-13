"""
Alembic 异步迁移环境配置

使用 asyncpg 驱动连接 PostgreSQL 15+。
支持在线迁移（无需额外配置 asyncio 模式）。
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

from app.config import get_settings
from app.database import Base

# 导入所有模型确保 metadata 注册
import app.models  # noqa: F401

# Alembic Config 对象
config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata 目标
target_metadata = Base.metadata

# 数据库 URL（从 app.config 获取，覆盖 alembic.ini 中的值）
settings = get_settings()


def run_migrations_offline() -> None:
    """
    离线模式：仅生成 SQL 脚本，不连接数据库。
    """
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """在线事务中执行迁移"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    异步在线模式：连接 PostgreSQL，执行迁移。
    这是默认模式（运行 `alembic upgrade head` 时触发）。
    """
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,  # 迁移时不使用连接池
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """入口：运行异步迁移"""
    asyncio.run(run_async_migrations())


# ── 选择模式 ──
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
