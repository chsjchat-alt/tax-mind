"""
认证 API 路由

提供：
  - POST /auth/register  用户注册（需指定租户）
  - POST /auth/login     OAuth2 密码流登录（返回 tenant-scoped JWT）
  - POST /auth/refresh   刷新 Token
  - GET  /auth/me        获取当前登录用户信息
"""
from datetime import datetime, timezone
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.models.tenant import Tenant
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
)
from app.api.deps import get_current_user
from app.config import get_settings
from app.utils.response import success_response

settings = get_settings()

# ── 内存频率限制 ──
# 注意：进程内实现仅适用于单实例部署；多副本/负载均衡场景应替换为 Redis 集中限流
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    """提取真实客户端 IP：优先取 X-Forwarded-For 第一个地址（反向代理场景）"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    """检查是否超过频率限制。返回 True 表示未超限。"""
    now = time.time()
    cutoff = now - window_seconds
    _rate_limit_store[key] = [t for t in _rate_limit_store[key] if t > cutoff]
    if len(_rate_limit_store[key]) >= max_attempts:
        return False
    _rate_limit_store[key].append(now)
    return True


router = APIRouter(prefix="/auth", tags=["认证"])


def _user_to_response(user: User) -> dict:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        enterprise_id=user.enterprise_id,
        tenant_id=user.tenant_id,
        role=user.role if isinstance(user.role, str) else user.role.value,
        is_active=user.is_active,
    ).model_dump()


@router.post("/register", summary="用户注册")
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """注册新用户（必须指定租户，默认为 viewer 角色）"""
    # 频率限制：同 IP 每小时最多 3 次注册
    client_ip = _client_ip(request)
    if not _check_rate_limit(f"register:{client_ip}", 3, 3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="注册请求过于频繁，请稍后再试",
        )

    # 校验租户是否存在
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.slug == body.tenant_slug)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户不存在: {body.tenant_slug}",
        )
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="租户已被禁用",
        )

    # 检查用户名是否已存在
    existing = await db.execute(
        select(User).where(User.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    # 检查邮箱是否已存在
    if body.email:
        email_existing = await db.execute(
            select(User).where(User.email == body.email)
        )
        if email_existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="邮箱已被注册",
            )

    # 校验 enterprise_id 是否属于当前租户
    if body.enterprise_id:
        from app.models.enterprise import Enterprise
        ent_check = await db.execute(
            select(Enterprise).where(
                Enterprise.id == body.enterprise_id,
                Enterprise.tenant_id == tenant.id,
            )
        )
        if not ent_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="关联企业不存在或不属于当前租户",
            )

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        tenant_id=tenant.id,
        enterprise_id=body.enterprise_id,
        role=UserRole.VIEWER,  # 强制最低权限，防止客户端提权
    )
    db.add(user)
    await db.flush()

    return success_response(
        data=_user_to_response(user),
        message="注册成功",
    )


@router.post("/login", summary="用户登录")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """OAuth2 密码流：用户名 + 密码换取 tenant-scoped JWT Token"""
    # 频率限制：同 IP 每分钟最多 5 次登录尝试
    client_ip = _client_ip(request)
    if not _check_rate_limit(f"login:{client_ip}", 5, 60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录请求过于频繁，请稍后再试",
        )

    result = await db.execute(
        select(User).where(User.username == body.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)

    access_token = create_access_token(
        user_id=user.id, username=user.username, tenant_id=user.tenant_id,
    )
    refresh_token = create_refresh_token(
        user_id=user.id, username=user.username, tenant_id=user.tenant_id,
    )

    return success_response(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        ).model_dump(),
        message="登录成功",
    )


@router.post("/refresh", summary="刷新 Token")
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """使用 refresh_token 获取新的 access_token"""
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 refresh_token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 类型错误",
        )

    user_id = payload.get("sub")
    username = payload.get("username")
    tenant_id = payload.get("tenant_id")

    # 校验用户和租户仍有效
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.is_active == True,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户或租户已失效",
        )

    new_access_token = create_access_token(
        user_id=user_id, username=username, tenant_id=tenant_id,
    )
    new_refresh_token = create_refresh_token(
        user_id=user_id, username=username, tenant_id=tenant_id,
    )

    return success_response(
        data=TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        ).model_dump(),
        message="Token 刷新成功",
    )


@router.get("/me", summary="获取当前用户")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """获取当前登录用户的个人信息"""
    return success_response(data=_user_to_response(current_user))
