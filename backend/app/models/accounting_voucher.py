"""
会计凭证表 (accounting_vouchers) + 会计分录表 (journal_entries)

支持完整的复式记账（借贷分录），每张凭证关联多条分录。
符合《企业会计准则——基本准则》对记账凭证要素的要求。
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, DateTime, Date, Enum as SAEnum,
    ForeignKey, Text, func, JSON, Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class VoucherType(str, enum.Enum):
    """凭证类型"""
    RECEIPT = "receipt"         # 收款凭证
    PAYMENT = "payment"         # 付款凭证
    TRANSFER = "transfer"       # 转账凭证
    ADJUSTMENT = "adjustment"   # 调整凭证


class EntryDirection(str, enum.Enum):
    """借贷方向"""
    DEBIT = "debit"    # 借
    CREDIT = "credit"  # 贷


class AccountingVoucher(Base):
    """会计凭证 — 记账凭证主表"""
    __tablename__ = "accounting_vouchers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(__import__("uuid").uuid4()),
    )
    enterprise_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("enterprises.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="企业ID",
    )

    voucher_no: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="凭证编号（如 记-2025-06-001）",
    )
    voucher_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="凭证日期",
    )
    voucher_type: Mapped[VoucherType] = mapped_column(
        SAEnum(VoucherType, name="voucher_type_enum", create_type=True),
        nullable=False, comment="凭证类型",
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="摘要",
    )
    attachment_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="附件张数",
    )

    # ── 审核与过账 ──
    reviewer: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="审核人",
    )
    is_posted: Mapped[bool] = mapped_column(
        default=False, comment="是否已过账",
    )

    # ── 元数据 ──
    source_system: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="来源系统",
    )
    extra_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="扩展元数据",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # ── 关联 ──
    entries = relationship(
        "JournalEntry", back_populates="voucher", cascade="all, delete-orphan",
    )
    enterprise = relationship("Enterprise", back_populates="accounting_vouchers")

    def __repr__(self) -> str:
        return f"<Voucher({self.voucher_no}) {self.voucher_date}>"


class JournalEntry(Base):
    """会计分录 — 凭证明细行（借贷分录）"""
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(__import__("uuid").uuid4()),
    )
    voucher_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounting_vouchers.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="凭证ID",
    )

    entry_line: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="分录行号（从1开始）",
    )
    direction: Mapped[EntryDirection] = mapped_column(
        SAEnum(EntryDirection, name="entry_direction_enum", create_type=True),
        nullable=False, comment="借贷方向",
    )
    account_code: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="科目代码",
    )
    account_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="科目名称",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, comment="金额",
    )
    description: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="分录摘要",
    )
    auxiliary: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="辅助核算（客商、项目、部门等）",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # ── 关联 ──
    voucher = relationship("AccountingVoucher", back_populates="entries")

    def __repr__(self) -> str:
        return (
            f"<Entry #{self.entry_line} "
            f"{'借' if self.direction == EntryDirection.DEBIT else '贷'} "
            f"{self.account_code} {self.amount}>"
        )
