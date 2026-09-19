"""add task verification columns (V4 §3.2 remediation-rate evidence)

Revision ID: 011
Revises: 010
Create Date: 2026-09-19

V4 §3.2 评分定义卡：整改率 = 已验证整改项权重 ÷ 可整改项权重，
「已验证」以整改证据经人工确认并回溯留痕为准。

本迁移为 remediation_tasks 增加人工验证三字段（verified_by /
verified_at / verify_note），并按产品决策（Q6）将历史已完成任务
批量标记为「已验证」（verified_at 取 completed_at，备注留痕），
避免存量企业评分因口径切换无故跳升。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "remediation_tasks",
        sa.Column("verified_by", sa.String(36), nullable=True,
                  comment="验证确认人用户ID"),
    )
    op.add_column(
        "remediation_tasks",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True,
                  comment="人工验证确认时间"),
    )
    op.add_column(
        "remediation_tasks",
        sa.Column("verify_note", sa.Text(), nullable=True,
                  comment="验证确认备注（证据留痕）"),
    )
    # Q6：历史已完成任务默认已验证（verified_at 取完成时间，留迁移痕记）
    op.execute(
        "UPDATE remediation_tasks "
        "SET verified_at = COALESCE(completed_at, CURRENT_TIMESTAMP), "
        "    verify_note = '历史数据迁移：默认已验证' "
        "WHERE status = 'completed' AND verified_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("remediation_tasks", "verify_note")
    op.drop_column("remediation_tasks", "verified_at")
    op.drop_column("remediation_tasks", "verified_by")
