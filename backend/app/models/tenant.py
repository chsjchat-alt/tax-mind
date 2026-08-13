"""
租户模型 (tenants)

多租户数据隔离核心：每个租户拥有独立的 用户+企业+数据 命名空间。
"""
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_gen_uuid,
        comment="租户ID",
    )
    name: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False,
        comment="租户名称（组织/公司名）",
    )
    slug: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
        comment="租户标识（URL-friendly 短码）",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="是否激活",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(),
    )

    # 关联
    users = relationship("User", back_populates="tenant")
    enterprises = relationship("Enterprise", back_populates="tenant")

    def __repr__(self) -> str:
        return f"<Tenant({self.slug}) active={self.is_active}>"
