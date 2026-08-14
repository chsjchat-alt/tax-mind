"""create risk_score_trajectory table

Revision ID: 007
Revises: 006
Create Date: 2026-08-14

新增风险评分轨迹表：记录每次整改 / 重评估前后的评分演化
（说明书 §4.2 B3「持久化评分轨迹表」），支撑「整改前后评分演化展示」。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_score_trajectory",
        sa.Column("id", sa.String(36), primary_key=True, comment="轨迹ID"),
        sa.Column(
            "enterprise_id", sa.String(36),
            sa.ForeignKey("enterprises.id", ondelete="CASCADE"),
            nullable=False, index=True, comment="企业ID",
        ),
        sa.Column(
            "assessment_date", sa.DateTime(timezone=True),
            nullable=False, comment="评估日期",
        ),
        sa.Column(
            "before_score", sa.Numeric(5, 2), nullable=True,
            comment="整改/重评估前风险分（0-100）",
        ),
        sa.Column(
            "after_score", sa.Numeric(5, 2), nullable=False,
            comment="整改/重评估后风险分（0-100）",
        ),
        sa.Column("before_level", sa.String(20), nullable=True, comment="前风险等级"),
        sa.Column("after_level", sa.String(20), nullable=False, comment="后风险等级"),
        sa.Column(
            "level_jump", sa.String(10), nullable=False, server_default="same",
            comment="等级跃迁方向（up 恶化 / down 改善 / same 不变）",
        ),
        sa.Column(
            "changed_by", sa.String(20), nullable=False,
            comment="变化来源（remediation 整改完成 / risk_scan 例行重评）",
        ),
        sa.Column(
            "reason", sa.String(500), nullable=False, server_default="",
            comment="变化原因说明",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), comment="创建时间",
        ),
    )


def downgrade() -> None:
    op.drop_table("risk_score_trajectory")
