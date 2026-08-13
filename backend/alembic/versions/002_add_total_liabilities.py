"""add total_liabilities to financial_statements

Revision ID: 002
Revises: 001
Create Date: 2026-07-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'financial_statements',
        sa.Column('total_liabilities', sa.Numeric(15, 2), default=0,
                  comment='总负债'),
    )


def downgrade() -> None:
    op.drop_column('financial_statements', 'total_liabilities')
