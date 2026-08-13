"""
心理画像表 (psychological_profiles)

重构版：
- deviation_index 字段升级为 NUMERIC(5,2) 保持不变
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Integer, Numeric, DateTime, ForeignKey, func,
    String, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PsychologicalProfile(Base):
    __tablename__ = "psychological_profiles"

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

    # ── 六维心理得分 ──
    control_desire_score: Mapped[int] = mapped_column(
        Integer, default=0, comment="掌控欲得分",
    )
    loss_aversion_score: Mapped[int] = mapped_column(
        Integer, default=0, comment="损失厌恶得分",
    )
    optimism_bias_score: Mapped[int] = mapped_column(
        Integer, default=0, comment="乐观偏差得分",
    )
    control_illusion_score: Mapped[int] = mapped_column(
        Integer, default=0, comment="控制错觉得分",
    )
    short_termism_score: Mapped[int] = mapped_column(
        Integer, default=0, comment="短期主义得分",
    )
    defensiveness_score: Mapped[int] = mapped_column(
        Integer, default=0, comment="防御心理得分",
    )

    # ── 复合指标 ──
    deviation_index: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"),
        comment="偏差指数（0-100 标准化）",
    )
    dominant_biases: Mapped[dict] = mapped_column(
        JSON, default=list,
        comment="主导偏差类型列表（中文名）",
    )
    intervention_strategy: Mapped[dict] = mapped_column(
        JSON, default=dict,
        comment="干预策略推荐（中文键）",
    )
    business_narrative: Mapped[str | None] = mapped_column(
        String(2000), nullable=True,
        comment="商业语言输出（老板能看懂的文字报告）",
    )
    technical_summary: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="技术摘要（包含元数据和引文信息）",
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
        "Enterprise", back_populates="psychological_profiles",
    )

    def __repr__(self) -> str:
        return (
            f"<PsychProfile({self.id[:8]}) "
            f"deviation={self.deviation_index}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
