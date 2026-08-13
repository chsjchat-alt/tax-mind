"""审计日志表

Revision ID: 005
Revises: 004
Create Date: 2026-07-17

创建 audit_logs 表，记录所有 API 请求操作审计信息。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True, comment="日志ID"),
        sa.Column("user_id", sa.String(36), nullable=True, index=True, comment="操作用户ID"),
        sa.Column("username", sa.String(50), nullable=True, comment="操作用户名"),
        sa.Column("tenant_id", sa.String(36), nullable=True, comment="租户ID"),
        sa.Column("method", sa.String(10), nullable=False, comment="HTTP 方法"),
        sa.Column("path", sa.String(500), nullable=False, comment="请求路径"),
        sa.Column("status_code", sa.Integer(), nullable=False, comment="HTTP 状态码"),
        sa.Column("business_code", sa.Integer(), nullable=True, comment="业务响应码"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, comment="请求耗时(ms)"),
        sa.Column("ip_address", sa.String(45), nullable=True, comment="客户端IP"),
        sa.Column("user_agent", sa.String(500), nullable=True, comment="User-Agent"),
        sa.Column("request_body", sa.Text(), nullable=True, comment="请求体(截断10KB)"),
        sa.Column("response_summary", sa.Text(), nullable=True, comment="响应摘要(截断1KB)"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_audit_logs_tenant_created", "audit_logs", ["tenant_id", "created_at"])
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])
    op.create_index("ix_audit_logs_path_method", "audit_logs", ["path", "method"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_path_method")
    op.drop_index("ix_audit_logs_user_created")
    op.drop_index("ix_audit_logs_tenant_created")
    op.drop_table("audit_logs")
