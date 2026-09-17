"""
企业信息表 (enterprises)

重构版：
- 新增 FK → industry_benchmarks
- 新增 is_internal_control_failed（内控系统性崩溃标志）
- 风险等级拓展为多维动态评级（RiskLevelEnhanced）
- 所有金额字段强制 NUMERIC(15,4)，比率字段强制 NUMERIC(10,4)
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String, Boolean, Numeric, Integer, DateTime,
    Enum as SAEnum, ForeignKey, func, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


# ── 枚举类型 ────────────────────────────────────────────
class IndustryType(str, enum.Enum):
    WHOLESALE_RETAIL = "批发零售"
    MANUFACTURING = "制造"
    CONSTRUCTION = "建筑"
    E_COMMERCE = "电商"
    CATERING = "餐饮服务"


class RiskLevelEnhanced(str, enum.Enum):
    """多维动态风险等级"""
    CRITICAL = "critical"       # 严重：>80分，建议立即稽查
    HIGH = "high"               # 高风险：60-80分
    MEDIUM_HIGH = "medium_high" # 中高：45-60分
    MEDIUM = "medium"           # 中等：30-45分
    LOW = "low"                 # 低风险：<30分


class Enterprise(Base):
    __tablename__ = "enterprises"

    # ── 主键 ──
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: _gen_uuid(),
        comment="企业ID",
    )

    # ── 租户隔离 ──
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="所属租户ID",
    )

    # ── 基本信息 ──
    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="企业名称",
    )
    credit_code: Mapped[str] = mapped_column(
        String(18), unique=True, nullable=False,
        comment="统一社会信用代码（18位）",
    )

    # ── 行业与基准关联 ──
    industry: Mapped[IndustryType] = mapped_column(
        SAEnum(IndustryType, name="industry_type_enum", create_type=True),
        nullable=False,
        comment="行业类型",
    )
    industry_benchmark_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("industry_benchmarks.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联行业基准ID（用于税负率/成本率对标）",
    )

    # ── 财务指标（NUMERIC(15,4) 精度红线） ──
    revenue_annual: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment="年营收（元）",
    )
    employee_count: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="员工人数",
    )

    # ── 税率/费率（NUMERIC(10,4) 精度红线） ──
    tax_rate_claimed: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"),
        comment="企业申报税负率",
    )
    cost_rate_claimed: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"),
        comment="企业申报成本费用率",
    )

    # ── 企业属性 ──
    is_high_tech: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否高新技术企业（享 15% 优惠税率）",
    )
    is_small_micro: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="是否小微企业（享所得税减免）",
    )
    is_internal_control_failed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="内控体系是否系统性崩溃（四流匹配<40%且连续3期高风险即触发）",
    )

    # ── 一票否决输入（纳税信用 / 涉税犯罪）──
    # 依据：《纳税缴费信用管理办法》国家税务总局公告 2025 年第 12 号（直接判D）
    #       《刑法》第 201 条（逃税罪刑事红线）
    tax_credit_level: Mapped[str | None] = mapped_column(
        String(2), nullable=True, default=None,
        comment="纳税信用等级（A/B/C/D，2025 年第 12 号）；D 级触发一票否决",
    )
    tax_crime_convicted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="是否因涉税犯罪（《刑法》第 201 条）被生效判决；触发一票否决",
    )

    # ── 多维风险评级 ──
    risk_level: Mapped[RiskLevelEnhanced] = mapped_column(
        SAEnum(RiskLevelEnhanced, name="risk_level_enhanced_enum",
               create_type=True),
        default=RiskLevelEnhanced.LOW, nullable=False,
        comment="当前风险等级（critical/high/medium_high/medium/low）",
    )
    risk_score_composite: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"),
        comment="综合风险评分（0-100，加权均值）",
    )
    consecutive_high_risk_periods: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="连续高风险期数（≥3期且四流匹配<40%触发内控崩溃）",
    )

    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(),
    )

    # ── 表级约束 ──
    __table_args__ = (
        CheckConstraint(
            "risk_score_composite >= 0 AND risk_score_composite <= 100",
            name="ck_risk_score_range",
        ),
    )

    # ── 关联 ────────────────────────────────────────────
    tenant = relationship("Tenant", back_populates="enterprises")
    industry_benchmark = relationship(
        "IndustryBenchmark", back_populates="enterprises",
    )
    bank_transactions = relationship(
        "BankTransaction", back_populates="enterprise",
    )
    invoices = relationship(
        "Invoice", back_populates="enterprise",
    )
    tax_declarations = relationship(
        "TaxDeclaration", back_populates="enterprise",
    )
    contracts = relationship(
        "Contract", back_populates="enterprise",
    )
    financial_statements = relationship(
        "FinancialStatement", back_populates="enterprise",
    )
    risk_assessments = relationship(
        "RiskAssessment", back_populates="enterprise",
    )
    remediation_tasks = relationship(
        "RemediationTask", back_populates="enterprise",
    )
    risk_score_trajectories = relationship(
        "RiskScoreTrajectory", back_populates="enterprise",
    )
    accounting_vouchers = relationship(
        "AccountingVoucher", back_populates="enterprise",
    )

    def __repr__(self) -> str:
        return (
            f"<Enterprise({self.name}) "
            f"industry={self.industry} risk={self.risk_level.value}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
