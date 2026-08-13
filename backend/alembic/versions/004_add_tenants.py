"""多租户数据隔离

Revision ID: 004
Revises: 003
Create Date: 2026-07-16

- 创建 tenants 表
- users 表添加 tenant_id FK（NOT NULL, CASCADE）
- enterprises 表添加 tenant_id FK（NOT NULL, CASCADE）
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 创建 tenants 表
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True, comment="租户ID"),
        sa.Column("name", sa.String(200), unique=True, nullable=False, comment="租户名称"),
        sa.Column("slug", sa.String(50), unique=True, nullable=False, index=True, comment="租户标识"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true"), comment="是否激活"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. users 表添加 tenant_id
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "tenant_id",
                sa.String(36),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                server_default="__no_tenant__",  # 临时默认值，迁移后手动处理
                comment="所属租户ID",
            )
        )
        batch.create_index("ix_users_tenant_id", ["tenant_id"])

    # 3. enterprises 表添加 tenant_id
    with op.batch_alter_table("enterprises") as batch:
        batch.add_column(
            sa.Column(
                "tenant_id",
                sa.String(36),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                server_default="__no_tenant__",
                comment="所属租户ID",
            )
        )
        batch.create_index("ix_enterprises_tenant_id", ["tenant_id"])


def downgrade() -> None:
    with op.batch_alter_table("enterprises") as batch:
        batch.drop_index("ix_enterprises_tenant_id")
        batch.drop_column("tenant_id")

    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_tenant_id")
        batch.drop_column("tenant_id")

    op.drop_table("tenants")
