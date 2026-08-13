"""
认证安全模块

提供：
  - bcrypt 密码哈希 / 校验
  - JWT access token / refresh token 签发
  - JWT token 解码与校验
"""
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
import bcrypt

from app.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希"""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希是否匹配"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(
    user_id: str,
    username: str,
    tenant_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """签发 JWT Access Token"""
    to_encode = {
        "sub": user_id,
        "username": username,
        "tenant_id": tenant_id,
        "type": "access",
    }
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    user_id: str,
    username: str,
    tenant_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """签发 JWT Refresh Token"""
    to_encode = {
        "sub": user_id,
        "username": username,
        "tenant_id": tenant_id,
        "type": "refresh",
    }
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(days=settings.jwt_refresh_token_expire_days)
    )
    to_encode["exp"] = expire
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    """解码并校验 JWT Token，返回 payload；校验失败抛出 JWTError"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        raise
