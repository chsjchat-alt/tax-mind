"""整改追踪 API Schemas"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RemediationTaskCreate(BaseModel):
    """创建整改任务"""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    priority: str = Field(default="medium", description="high/medium/low")
    due_date: Optional[date] = None
    risk_assessment_id: Optional[UUID] = None
    source: str = Field(default="manual", description="任务来源: manual/compliance")
    compliance_tags: Optional[list[str]] = Field(
        default=None,
        description="关联合规发现的 rule_key 列表（source=compliance 时有效）",
    )


class RemediationTaskUpdate(BaseModel):
    """更新整改任务"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    progress: Optional[float] = Field(None, ge=0, le=100)
    compliance_tags: Optional[list[str]] = None
    feedback_notes: Optional[str] = Field(None, max_length=5000)


class RemediationTaskResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    risk_assessment_id: Optional[UUID]
    source: Optional[str] = None
    compliance_tags: Optional[list[str]] = None
    feedback_notes: Optional[str] = None
    title: str
    description: str
    priority: str
    status: str
    due_date: Optional[date]
    completed_at: Optional[datetime]
    progress: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RemediationTaskListResponse(BaseModel):
    tasks: list[RemediationTaskResponse]
    total: int
