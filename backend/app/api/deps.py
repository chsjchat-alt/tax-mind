"""
API 依赖注入

所有API通过 deps.py 获取：
  - 数据库会话 (get_db)
  - 当前登录用户 (get_current_user)
  - 当前租户ID (get_current_tenant_id)
  - 租户隔离的企业查询辅助 (get_tenant_enterprise)
  - RBAC 角色依赖 (require_admin / require_auditor / require_viewer)
  - 统一响应格式 (success_response / error_response)
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.models.enterprise import Enterprise
from app.core.security import decode_token
from app.core.permissions import check_role, ROLE_HIERARCHY
from app.utils.response import success_response, error_response

# ── OAuth2 Bearer Token 提取器 ──
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scheme_name="JWT",
    description="输入 Bearer {access_token}",
)


async def _parse_jwt_payload(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """解析并校验 JWT Token，返回 payload"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except Exception:
        raise credentials_exception

    token_type: str | None = payload.get("type")
    if token_type != "access":
        raise credentials_exception

    return payload


async def get_current_tenant_id(
    payload: dict = Depends(_parse_jwt_payload),
) -> str:
    """从 JWT 提取当前租户ID"""
    tenant_id: str | None = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少租户信息",
        )
    return tenant_id


async def get_current_user(
    payload: dict = Depends(_parse_jwt_payload),
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT Token 解析当前登录用户，校验租户归属后注入"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return user


async def get_tenant_enterprise(
    enterprise_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> Enterprise:
    """
    按租户+企业ID获取企业，自动执行租户隔离。

    用法替代直接的 enterprise 查询：
        enterprise = Depends(get_tenant_enterprise)
    """
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"企业不存在或无权访问: {enterprise_id}",
        )
    return enterprise


async def get_enterprise_or_403(
    ent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Enterprise:
    """
    按企业ID获取企业并校验租户归属（租户隔离安全加固）。

    与 get_tenant_enterprise 的区别：
      - 租户来源是当前登录用户对象（current_user.tenant_id）；
      - 企业不存在或租户不一致统一抛出 403（避免跨租户探测企业存在性）。

    用法（在端点函数体内直接调用，复用已注入的 current_user / db）：
        await get_enterprise_or_403(ent_id, current_user, db)
    """
    result = await db.execute(
        select(Enterprise).where(Enterprise.id == ent_id)
    )
    enterprise = result.scalar_one_or_none()
    if not enterprise or enterprise.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"企业不存在或无权访问: {ent_id}",
        )
    return enterprise


# ── RBAC 角色依赖（工厂函数，在 deps.py 定义以避免循环导入） ──

def _make_role_dep(*roles: UserRole):
    """创建角色检查依赖：先通过 get_current_user 获取用户，再校验角色"""

    async def checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        check_role(current_user, roles)
        return current_user

    return checker


require_viewer = _make_role_dep(UserRole.VIEWER)
require_auditor = _make_role_dep(UserRole.AUDITOR)
require_admin = _make_role_dep(UserRole.ADMIN)
require_admin_or_auditor = _make_role_dep(UserRole.ADMIN, UserRole.AUDITOR)


__all__ = [
    "success_response",
    "error_response",
    "get_db",
    "get_current_user",
    "get_current_tenant_id",
    "get_tenant_enterprise",
    "get_enterprise_or_403",
    "oauth2_scheme",
    "require_admin",
    "require_auditor",
    "require_viewer",
    "require_admin_or_auditor",
]
