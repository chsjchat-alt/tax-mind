"""
合同台账表 (contracts)

重构版：
- 金额字段强制 NUMERIC(15,4)
- 新增 flow_validation_key（四流一致性跨表校验关联键）
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, Date, DateTime,
    Enum as SAEnum, ForeignKey, func, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base
from app.models.fields import EncryptedString


class ContractType(str, enum.Enum):
    SALES = "sales"             # 销售合同
    PURCHASE = "purchase"       # 采购合同


class Contract(Base):
    __tablename__ = "contracts"

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

    # ── 合同基本信息 ──
    contract_no: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="合同编号",
    )
    contract_type: Mapped[ContractType] = mapped_column(
        SAEnum(ContractType, name="contract_type_enum",
               create_type=True),
        nullable=False, comment="合同类型：sales 销售 / purchase 采购",
    )
    counterparty: Mapped[str] = mapped_column(
        EncryptedString, nullable=False,
        comment="合同对方（公司名，AES-256-GCM 加密存储）",
    )

    # ── 金额字段（NUMERIC(15,4) 精度红线） ──
    contract_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False,
        comment="合同金额",
    )

    # ── 日期与状态 ──
    signing_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="签订日期",
    )
    execution_status: Mapped[str] = mapped_column(
        String(50), default="进行中", comment="执行状态",
    )

    # ── 四流一致性跨表校验 ────────────────────────────────
    flow_validation_key: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True,
        comment=(
            "四流一致性跨表校验关联键（SHA256哈希）。"
            "由 contract_no + counterparty 生成，"
            "用于跨表 JOIN 校验合同流/资金流/发票流一致性。"
        ),
    )
    flow_deviation_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment=(
            "合同流偏离度元数据：\n"
            "  - paid_amount: 已支付金额 vs 合同额\n"
            "  - invoiced_amount: 已开票金额 vs 合同额\n"
            "  - discrepancy_flag: 是否存在金额不一致"
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
        "Enterprise", back_populates="contracts",
    )

    def __repr__(self) -> str:
        return (
            f"<Contract({self.contract_no}) "
            f"type={self.contract_type.value} ¥{self.contract_amount}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
