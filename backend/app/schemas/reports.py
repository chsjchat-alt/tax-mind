"""报告生成 API Schemas"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    """生成报告请求"""
    include_simulation: bool = Field(default=True, description="是否包含风险模拟")


class ReportResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    title: str
    report_type: str
    generated_at: datetime
    content_summary: dict

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    reports: list[ReportResponse]
    total: int


class ReportDetailResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    title: str
    report_type: str
    generated_at: datetime
    content: dict
    risk_assessment_id: Optional[UUID]

    model_config = {"from_attributes": True}
