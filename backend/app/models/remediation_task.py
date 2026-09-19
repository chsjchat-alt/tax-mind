"""
整改任务表 (remediation_tasks)

重构版：
- progress NUMERIC(5,2) 保持不变
"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, Date, DateTime, Enum as SAEnum,
    ForeignKey, func, Text, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class TaskPriority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class RemediationTask(Base):
    __tablename__ = "remediation_tasks"

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
    risk_assessment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("risk_assessments.id", ondelete="SET NULL"),
        nullable=True, comment="关联风险评估ID",
    )

    # ── 任务信息 ──
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="整改任务标题",
    )
    description: Mapped[str] = mapped_column(
        String(2000), default="", comment="任务描述",
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(TaskPriority, name="task_priority_enum",
               create_type=True),
        default=TaskPriority.MEDIUM, nullable=False, comment="优先级",
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status_enum",
               create_type=True),
        default=TaskStatus.PENDING, nullable=False, comment="状态",
    )

    # ── 任务来源与关联 ──
    source: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="manual",
        comment="任务来源: manual=手动创建, compliance=合规校验自动生成",
    )
    compliance_tags: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
        comment="关联的合规校验发现（rule_key列表）",
    )
    feedback_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="效果反馈备注",
    )

    # ── 时间与进度 ──
    due_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="截止日期",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间",
    )
    progress: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"),
        comment="进度百分比（0-100）",
    )

    # ── 人工验证（V4 §3.2 整改率分子「已验证整改项」的认定依据）──
    # 完成任务 ≠ 已验证：整改证据须经 auditor/admin 人工确认并留痕后，
    # 才计入整改率分子（合规调整引擎 compliance_adjustment）。
    verified_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="验证确认人用户ID",
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="人工验证确认时间",
    )
    verify_note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="验证确认备注（证据留痕）",
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
        "Enterprise", back_populates="remediation_tasks",
    )
    risk_assessment = relationship(
        "RiskAssessment", back_populates="remediation_tasks",
    )

    def __repr__(self) -> str:
        return (
            f"<RemTask({self.id[:8]}) "
            f"title={self.title[:30]} status={self.status.value}>"
        )


def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
