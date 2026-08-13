"""添加 users 表 - JWT + OAuth2 认证 + RBAC 角色

Revision ID: 003
Revises: 002
Create Date: 2026-07-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True, comment="用户ID"),
        sa.Column(
            "username",
            sa.String(50),
            unique=True,
            nullable=False,
            index=True,
            comment="登录用户名",
        ),
        sa.Column(
            "email",
            sa.String(100),
            unique=True,
            nullable=True,
            comment="电子邮箱",
        ),
        sa.Column(
            "hashed_password",
            sa.String(128),
            nullable=False,
            comment="bcrypt 哈希密码",
        ),
        sa.Column("full_name", sa.String(100), nullable=True, comment="姓名"),
        sa.Column(
            "enterprise_id",
            sa.String(36),
            nullable=True,
            comment="关联企业ID",
        ),
        sa.Column(
            "role",
            sa.String(10),
            nullable=False,
            server_default="viewer",
            comment="RBAC 角色: admin / auditor / viewer",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否激活",
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后登录时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
