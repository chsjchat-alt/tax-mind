"""
银行流水表 (bank_transactions)

重构版：
- 金额字段强制 NUMERIC(15,4)
- 新增四流一致性跨表校验关联键 (flow_validation_key)
- 新增资金流→物流→发票流偏离度元数据
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


class DirectionType(str, enum.Enum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class AccountType(str, enum.Enum):
    CORPORATE = "corporate"     # 对公账户
    PERSONAL = "personal"       # 个人账户（私卡收款风险指标）


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

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

    # ── 交易基本信息 ──
    transaction_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="交易日期",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False,
        comment="交易金额（NUMERIC(15,4)红线）",
    )
    direction: Mapped[DirectionType] = mapped_column(
        SAEnum(DirectionType, name="direction_type_enum",
               create_type=True),
        nullable=False, comment="方向：inflow 流入 / outflow 流出",
    )
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, name="account_type_enum",
               create_type=True),
        nullable=False, comment="账户类型：corporate 对公 / personal 个人",
    )

    # ── 对手与用途 ──
    account_holder: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True,
        comment="账户持有人（AES-256-GCM 加密存储）",
    )
    counterparty: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True,
        comment="交易对手（AES-256-GCM 加密存储）",
    )
    description: Mapped[str | None] = mapped_column(
        String(500), comment="交易摘要（银行备注）",
    )

    # ── 申报状态 ──
    is_declared: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否已申报纳税",
    )

    # ── 四流一致性跨表校验 ────────────────────────────────
    flow_validation_key: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True,
        comment=(
            "四流一致性跨表校验关联键（SHA256哈希）。"
            "由 contract_no + invoice_no + counterparty 拼接生成，"
            "用于跨表 JOIN 校验资金流/物流/发票流/合同流一致性。"
        ),
    )
    flow_deviation_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment=(
            "偏离度元数据 JSON：\n"
            "  - fund_flow_delta: 资金流与合同额偏差（元）\n"
            "  - logistics_match: 物流信息匹配状态\n"
            "  - invoice_match: 发票号码匹配状态\n"
            "  - is_anomaly: 是否存在四流不一致异常"
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
        "Enterprise", back_populates="bank_transactions",
    )

    def __repr__(self) -> str:
        return (
            f"<BankTxn({self.id[:8]}) "
            f"{self.direction.value} ¥{self.amount} "
            f"type={self.account_type.value}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
