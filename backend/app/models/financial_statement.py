"""
财务报表表 (financial_statements)

重构版：
- 所有金额字段强制 NUMERIC(15,4)
- 比率字段强制 NUMERIC(10,4)
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, DateTime, Enum as SAEnum,
    ForeignKey, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class StatementType(str, enum.Enum):
    BALANCE_SHEET = "balance_sheet"     # 资产负债表
    INCOME_STATEMENT = "income_statement"  # 利润表
    CASH_FLOW = "cash_flow"             # 现金流量表


class FinancialStatement(Base):
    __tablename__ = "financial_statements"

    # ── 主键 ──
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: _gen_uuid(),
    )
    enterprise_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("enterprises.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="企业ID",
    )

    # ── 报表标识 ──
    period: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="报表期间（如 2025-01）",
    )
    statement_type: Mapped[StatementType] = mapped_column(
        SAEnum(StatementType, name="statement_type_enum",
               create_type=True),
        nullable=False, comment="报表类型",
    )

    # ── 核心财务指标（NUMERIC(15,4) 精度红线） ──
    total_assets: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"), comment="总资产",
    )
    total_liabilities: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"), comment="总负债",
    )
    total_revenue: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"), comment="营业收入",
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"), comment="总成本费用",
    )
    net_profit: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"), comment="净利润",
    )
    operating_cash_flow: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment="经营活动现金流",
    )

    # ── 比率字段（NUMERIC(10,4) 精度红线） ──
    tax_burden_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"),
        comment="税负率 (= 实缴税额 / 营业收入)",
    )
    cost_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"),
        comment="成本费用率 (= 总成本 / 营业收入)",
    )

    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(),
    )

    # ── 关联 ──
    enterprise = relationship(
        "Enterprise", back_populates="financial_statements",
    )

    def __repr__(self) -> str:
        return (
            f"<FinStmt({self.id[:8]}) "
            f"period={self.period} type={self.statement_type.value}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
