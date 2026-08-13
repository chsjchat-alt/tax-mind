"""
风险评估结果表 (risk_assessments)

重构版（原 Phase 2 的 RiskAssessment 扩展）：
- 新增 tax_penetration_amount（个税穿透欠税规模）
- 新增 compound_penalty_exposure（复合罚款预期敞口）
- 所有金额字段强制 NUMERIC(15,4)
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Numeric, DateTime, Enum as SAEnum, ForeignKey, func,
    String, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class AssessRiskLevel(str, enum.Enum):
    """评估风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

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

    # ── 评估日期 ──
    assessment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="评估日期",
    )

    # ── 总体风险 ──
    overall_risk_level: Mapped[AssessRiskLevel] = mapped_column(
        SAEnum(AssessRiskLevel, name="assess_risk_level_enum",
               create_type=True),
        nullable=False, comment="总体风险等级",
    )
    overall_risk_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, comment="总体风险评分（0-100）",
    )

    # ── 四流匹配 ──
    four_flow_match_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), comment="四流匹配度（0-100）",
    )

    # ── 私卡与成本偏离 ──
    private_card_ratio: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"), comment="私卡收款占比",
    )
    cost_deviation: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"),
        comment="成本费用率偏离行业基准的百分点",
    )

    # ── 新增：穿透与敞口（NUMERIC(15,4) 精度红线） ──
    tax_penetration_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment=(
            "个税穿透欠税规模。穿透公私账户后，"
            "识别出的未代扣代缴个人所得税总额。"
        ),
    )
    compound_penalty_exposure: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=Decimal("0"),
        comment=(
            "复合罚款预期敞口。包括：\n"
            "  - 少缴税款 0.5-5 倍罚款\n"
            "  - 日万分之五滞纳金\n"
            "  - 虚开发票 1-5 倍罚款\n"
            "  - 复合计息下累计形成的总额预期敞口"
        ),
    )

    # ── 详情与建议 ──
    risk_details: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="各维度风险详情",
    )
    recommendations: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="整改建议",
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
        "Enterprise", back_populates="risk_assessments",
    )
    remediation_tasks = relationship(
        "RemediationTask", back_populates="risk_assessment",
    )

    def __repr__(self) -> str:
        return (
            f"<RiskAsmt({self.id[:8]}) "
            f"level={self.overall_risk_level.value} "
            f"score={self.overall_risk_score}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
