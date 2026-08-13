"""
纳税申报表 (tax_declarations)

重构版：
- 金额字段强制 NUMERIC(15,4)
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, Date, DateTime,
    Enum as SAEnum, ForeignKey, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class TaxType(str, enum.Enum):
    VAT = "vat"                         # 增值税
    INCOME_TAX = "income_tax"           # 企业所得税
    PERSONAL_INCOME_TAX = "personal_income_tax"  # 个人所得税


class TaxDeclaration(Base):
    __tablename__ = "tax_declarations"

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

    # ── 申报信息 ──
    tax_type: Mapped[TaxType] = mapped_column(
        SAEnum(TaxType, name="tax_type_enum", create_type=True),
        nullable=False, comment="税种",
    )
    period: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="申报期间（如 2025-Q1 或 2025-01）",
    )

    # ── 金额字段（NUMERIC(15,4) 精度红线） ──
    declared_revenue: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment="申报收入",
    )
    declared_tax: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment="申报税额",
    )
    actual_paid: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment="实际缴纳",
    )

    # ── 申报日期 ──
    declaration_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="申报日期",
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
        "Enterprise", back_populates="tax_declarations",
    )

    def __repr__(self) -> str:
        return (
            f"<TaxDecl({self.id[:8]}) "
            f"type={self.tax_type.value} period={self.period}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
