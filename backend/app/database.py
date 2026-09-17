"""
「蒙牛全产业链 AI 内生合规决策大脑」异步数据库连接池

使用 asyncpg 驱动连接 PostgreSQL 15+。
支持逻辑复制订阅、连接池管理和健康检查。
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import get_settings

settings = get_settings()

# ── 异步引擎 ──────────────────────────────────────────
_is_pg = "postgresql" in settings.database_url or "asyncpg" in settings.database_url

_engine_kwargs: dict = {"echo": settings.debug}

if _is_pg:
    # asyncpg 直连 PostgreSQL: 启用连接池和服务器配置
    _connect_args: dict = {
        "server_settings": {
            "application_name": "taxmind",
            "timezone": "Asia/Shanghai",
        },
        "command_timeout": 30,
    }

    # ── SSL/TLS 传输加密（等保 2.0 合规要求）──
    _ssl_mode = settings.db_ssl_mode
    if _ssl_mode:
        import ssl
        _ssl_ctx = ssl.create_default_context()
        if _ssl_mode == "require":
            _ssl_ctx.check_hostname = False
            _ssl_ctx.verify_mode = ssl.CERT_NONE
        elif _ssl_mode == "verify-ca":
            _ssl_ctx.check_hostname = False
            _ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        elif _ssl_mode == "verify-full":
            _ssl_ctx.check_hostname = True
            _ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        _connect_args["ssl"] = _ssl_ctx

    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args=_connect_args,
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)

# ── 会话工厂 ──────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """声明式基类，所有 ORM 模型继承此类"""
    pass


# ── FastAPI 依赖注入 ───────────────────────────────────
async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话（上下文管理器自动提交/回滚）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """初始化数据库表结构（原型阶段使用，产品阶段由 Alembic 接管）"""
    import app.models  # noqa: F401 — 触发模型注册
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_db_health() -> bool:
    """数据库健康检查"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
