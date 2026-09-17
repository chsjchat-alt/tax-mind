"""
「蒙牛全产业链 AI 内生合规决策大脑」配置管理

使用 pydantic-settings 从环境变量或 .env 文件加载配置。
生产环境强制 PostgreSQL + asyncpg，原型阶段可降级 SQLite。
"""
import pathlib

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""

    # ── 应用基本配置 ──
    app_name: str = "蒙牛全产业链 AI 内生合规决策大脑"
    app_version: str = "0.3.0"
    debug: bool = False

    # ── 数据库配置 ──
    # 必须通过环境变量注入，禁止硬编码凭据
    database_url: str = ""

    db_pool_size: int = 20
    db_max_overflow: int = 10
    # SSL/TLS 连接模式（require / verify-ca / verify-full / 留空禁用）
    # 等保 2.0 要求传输加密，生产环境至少设为 "require"
    db_ssl_mode: str = "require"

    # ── CORS 配置 ──
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # ── JWT 认证配置 ──
    # 必须通过环境变量注入，禁止硬编码（泄漏可伪造任意用户 Token）
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480  # 8 小时，开发环境避免频繁 401
    jwt_refresh_token_expire_days: int = 7

    # ── 字段加密配置 ──
    # AES-256-GCM 密钥（Base64编码，32字节），必须通过环境变量注入
    encryption_key: str = ""

    # ── 大模型 API 配置 ──
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    llm_provider: str = "deepseek"
    llm_timeout: int = 30
    llm_max_retries: int = 3

    model_config = {
        "env_file": str(pathlib.Path(__file__).parent.parent / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例（进程级缓存）"""
    s = Settings()
    _validate_settings(s)
    return s


def _validate_settings(settings: Settings) -> None:
    """启动时校验关键安全配置，缺失则拒绝启动"""
    missing = []
    if not settings.database_url:
        missing.append("DATABASE_URL")
    if not settings.jwt_secret_key:
        missing.append("JWT_SECRET_KEY")
    if not settings.encryption_key:
        missing.append("ENCRYPTION_KEY")
    if missing:
        raise RuntimeError(
            f"缺少必要的环境变量，服务拒绝启动: {', '.join(missing)}。"
            f"请在 .env 文件或环境变量中设置。"
        )

    # ── URL 归一化：托管平台（Railway/Render/Neon 等）默认给出
    #    postgresql://（同步驱动前缀），而本项目引擎使用 asyncpg，
    #    统一转换为 postgresql+asyncpg://，避免 create_async_engine 报错。
    if settings.database_url.startswith("postgresql://"):
        settings.database_url = settings.database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
