"""add audit_logs calculation_id and param_snapshot (audit evidence chain)

Revision ID: 009
Revises: 008
Create Date: 2026-09-12

V4 §二 审计证据链：为审计日志补充「计算 ID + 参数快照」要素——
报告层引用的每一个数值必须来自带计算 ID、参数快照与审计日志的确定性函数返回值。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column(
            "calculation_id",
            sa.String(length=64),
            nullable=True,
            comment="确定性计算实例哈希（审计证据链）",
        ),
    )
    op.add_column(
        "audit_logs",
        sa.Column(
            "param_snapshot",
            sa.Text(),
            nullable=True,
            comment="计算参数快照 JSON（规则ID集合 + 决策图版本 + 输入参数）",
        ),
    )
    op.create_index(
        "ix_audit_logs_calculation_id", "audit_logs", ["calculation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_calculation_id", table_name="audit_logs")
    op.drop_column("audit_logs", "param_snapshot")
    op.drop_column("audit_logs", "calculation_id")
