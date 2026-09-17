"""
RBAC 权限依赖检查器

角色层级（从低到高）：
  viewer  → 只读：查看企业、风险、干预等所有 GET 请求
  auditor → 读写：可触发风险扫描、模拟税务、合规检查等操作
  admin   → 管理：可创建/编辑/删除企业、管理用户

权限继承：高角色自动拥有低角色的所有权限。
"""
from typing import Sequence

from fastapi import HTTPException, status

from app.models.user import User, UserRole


ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.VIEWER: 1,
    UserRole.AUDITOR: 2,
    UserRole.ADMIN: 3,
}


def check_role(user: User, required_roles: Sequence[UserRole]) -> None:
    """校验用户角色是否满足要求，不满足则抛出 403"""
    user_level = ROLE_HIERARCHY.get(user.role, 0)
    for r in required_roles:
        if user_level >= ROLE_HIERARCHY.get(r, 99):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"权限不足，当前角色: {user.role.value}，需要: "
               f"{'/'.join(r.value for r in required_roles)}",
    )
