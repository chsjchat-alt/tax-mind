"""drop psychological_profiles table (V4 §5.4 boundary enforcement)

Revision ID: 010
Revises: 009
Create Date: 2026-09-12

V4 §5.4 明确边界：不做侵入式心理画像，不采用「心理干预」叙事；
一期仅采用微任务、积分、提醒等外部可观测的行为机制。
本迁移移除遗留的心理画像表，使 schema 与方案边界一致。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "ix_psychological_profiles_enterprise_id", table_name="psychological_profiles"
    )
    op.drop_table("psychological_profiles")


def downgrade() -> None:
    """降级：重建心理画像表（仅结构，与 001 初始定义一致，数据不可恢复）"""
    op.create_table(
        "psychological_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("enterprise_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False,
                  comment="企业ID"),
        sa.Column("assessment_date", sa.DateTime(timezone=True), nullable=False,
                  comment="评估日期"),
        sa.Column("control_desire_score", sa.Integer, default=0, comment="掌控欲得分"),
        sa.Column("loss_aversion_score", sa.Integer, default=0, comment="损失厌恶得分"),
        sa.Column("optimism_bias_score", sa.Integer, default=0, comment="乐观偏差得分"),
        sa.Column("control_illusion_score", sa.Integer, default=0, comment="控制错觉得分"),
        sa.Column("short_termism_score", sa.Integer, default=0, comment="短期主义得分"),
        sa.Column("defensiveness_score", sa.Integer, default=0, comment="防御心理得分"),
        sa.Column("deviation_index", sa.Numeric(5, 2), default=0, comment="偏差指数"),
        sa.Column("dominant_biases", postgresql.JSONB, default=list,
                  comment="主导偏差类型列表"),
        sa.Column("intervention_strategy", postgresql.JSONB, default=dict,
                  comment="干预策略推荐"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_psychological_profiles_enterprise_id",
        "psychological_profiles",
        ["enterprise_id"],
    )
