"""
审计日志模型 (audit_logs)

记录所有 API 请求的操作审计信息。
由中间件自动写入，不依赖业务代码手动调用。
"""
from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_gen_uuid,
        comment="日志ID",
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="操作用户ID（未认证则为 NULL）",
    )
    username: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="操作用户名",
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="租户ID",
    )
    method: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="HTTP 方法: GET/POST/PUT/DELETE",
    )
    path: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="请求路径",
    )
    status_code: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="HTTP 状态码",
    )
    business_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="业务响应码（从响应 body 提取）",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="请求耗时（毫秒）",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True,
        comment="客户端 IP 地址",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="客户端 User-Agent",
    )
    request_body: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="请求体（截断至 10KB，仅 POST/PUT）",
    )
    response_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="响应摘要（截断至 1KB）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True,
    )

    __table_args__ = (
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_path_method", "path", "method"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog({self.method} {self.path} {self.status_code})>"
