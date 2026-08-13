"""
发票数据表 (invoices)

重构版：
- 金额字段强制 NUMERIC(15,4)
- 新增 flow_validation_key（四流一致性跨表校验关联键）
- 新增物流/合同流匹配元数据
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, Date, Boolean, DateTime,
    Enum as SAEnum, ForeignKey, func, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base
from app.models.fields import EncryptedString


class InvoiceType(str, enum.Enum):
    INPUT = "input"             # 进项发票
    OUTPUT = "output"           # 销项发票


class Invoice(Base):
    __tablename__ = "invoices"

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

    # ── 发票基本信息 ──
    invoice_no: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="发票号码",
    )
    invoice_type: Mapped[InvoiceType] = mapped_column(
        SAEnum(InvoiceType, name="invoice_type_enum",
               create_type=True),
        nullable=False, comment="发票类型：input 进项 / output 销项",
    )
    invoice_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="开票日期",
    )

    # ── 金额字段（NUMERIC(15,4) 精度红线） ──
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False,
        comment="不含税金额",
    )
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment="税额",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False,
        comment="价税合计（= amount + tax_amount）",
    )

    # ── 商品与交易方 ──
    product_name: Mapped[str | None] = mapped_column(
        String(200), comment="商品/服务名称",
    )
    buyer_name: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True,
        comment="购方名称（AES-256-GCM 加密存储）",
    )
    seller_name: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True,
        comment="销方名称（AES-256-GCM 加密存储）",
    )

    # ── 数电票标志 ──
    is_digital: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否数电票（全数字化发票）",
    )

    # ── 四流一致性跨表校验 ────────────────────────────────
    flow_validation_key: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True,
        comment=(
            "四流一致性跨表校验关联键（SHA256哈希）。"
            "用于与 bank_transactions / contracts 做跨表 JOIN 校验。"
        ),
    )
    flow_deviation_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment=(
            "发票流偏离度元数据：\n"
            "  - contract_amount_match: 合同金额与发票金额偏差\n"
            "  - bank_amount_match: 银行流水金额与发票金额偏差\n"
            "  - is_ghost_invoice: 是否疑似虚开发票"
        ),
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
        "Enterprise", back_populates="invoices",
    )

    def __repr__(self) -> str:
        return (
            f"<Invoice({self.invoice_no}) "
            f"type={self.invoice_type.value} ¥{self.total_amount}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
