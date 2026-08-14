"""
风险评分轨迹表 (risk_score_trajectory)

记录每次整改 / 重评估前后的评分演化，支撑「整改前后评分演化展示」（A1）
与「等级跃迁」证据链（B3，对应说明书 §4.2）。

设计要点：
- before/after 均为风险分语义（越高越危险），数值约束 [0, 100]
- changed_by 标识变化来源：remediation（整改完成）/ risk_scan（例行重评）
- level_jump 表示等级跃迁方向：up（恶化）/ down（改善）/ same（不变）
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, DateTime, ForeignKey, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RiskScoreTrajectory(Base):
    __tablename__ = "risk_score_trajectory"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: _gen_uuid(),
        comment="轨迹ID",
    )
    enterprise_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("enterprises.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="企业ID",
    )

    # ── 评分演化 ──
    assessment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="评估日期",
    )
    before_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=True, comment="整改/重评估前风险分（0-100）",
    )
    after_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, comment="整改/重评估后风险分（0-100）",
    )
    before_level: Mapped[str] = mapped_column(
        String(20), nullable=True, comment="前风险等级",
    )
    after_level: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="后风险等级",
    )
    level_jump: Mapped[str] = mapped_column(
        String(10), nullable=False, default="same",
        comment="等级跃迁方向（up 恶化 / down 改善 / same 不变）",
    )

    # ── 来源与原因 ──
    changed_by: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="变化来源（remediation 整改完成 / risk_scan 例行重评）",
    )
    reason: Mapped[str] = mapped_column(
        String(500), default="", nullable=False, comment="变化原因说明",
    )

    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # ── 关联 ──
    enterprise = relationship("Enterprise", back_populates="risk_score_trajectories")

    def __repr__(self) -> str:
        return (
            f"<Trajectory({self.id[:8]}) "
            f"{self.before_score}→{self.after_score} "
            f"jump={self.level_jump} by={self.changed_by}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
