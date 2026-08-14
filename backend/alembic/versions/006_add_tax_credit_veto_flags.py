"""add tax credit veto flags to enterprises

Revision ID: 006
Revises: 005
Create Date: 2026-08-14

新增一票否决输入字段（依据 2025 年第 12 号 / 刑法第 201 条）：
- tax_credit_level: 纳税信用等级 A/B/C/D（D 级直接判级 → 一票否决）
- tax_crime_convicted: 涉税犯罪生效判决标志 → 一票否决
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "enterprises",
        sa.Column(
            "tax_credit_level", sa.String(2), nullable=True,
            comment="纳税信用等级（A/B/C/D，2025 年第 12 号）；D 级触发一票否决",
        ),
    )
    op.add_column(
        "enterprises",
        sa.Column(
            "tax_crime_convicted", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
            comment="是否因涉税犯罪（《刑法》第 201 条）被生效判决；触发一票否决",
        ),
    )


def downgrade() -> None:
    op.drop_column("enterprises", "tax_crime_convicted")
    op.drop_column("enterprises", "tax_credit_level")
