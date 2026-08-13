"""
用户认证表 (users)

支持 OAuth2 密码流 + JWT Bearer Token 认证 + RBAC 角色控制 + 多租户隔离。
"""
import enum
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.fields import EncryptedString


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    """RBAC 角色枚举"""
    ADMIN = "admin"       # 管理员：创建/编辑/删除企业，管理用户
    AUDITOR = "auditor"   # 审计员：触发风险扫描、模拟、合规检查
    VIEWER = "viewer"     # 查看者：只读访问所有数据


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=_gen_uuid,
        comment="用户ID",
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
        comment="登录用户名",
    )
    email: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True,
        comment="电子邮箱（AES-256-GCM 加密存储）",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="bcrypt 哈希密码",
    )
    full_name: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True,
        comment="姓名（AES-256-GCM 加密存储）",
    )
    # ── 租户隔离 ──
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="所属租户ID",
    )
    enterprise_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="关联企业ID（多用户可以关联同一企业）",
    )
    role: Mapped[UserRole] = mapped_column(
        String(10), default=UserRole.VIEWER, nullable=False,
        comment="RBAC 角色: admin / auditor / viewer",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="是否激活",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="最后登录时间",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(),
    )

    # 关联
    tenant = relationship("Tenant", back_populates="users")

    @property
    def is_superuser(self) -> bool:
        """兼容旧代码：admin 角色等同于超级管理员"""
        return self.role == UserRole.ADMIN

    def __repr__(self) -> str:
        return f"<User({self.username}) role={self.role.value} tenant={self.tenant_id}>"
