"""风险扫描 API Schemas"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RiskScanResponse(BaseModel):
    """风险扫描结果"""
    risk_assessment_id: str
    enterprise_id: str
    overall_risk_level: str  # low / medium / high
    overall_risk_score: float
    four_flow_match_score: float
    private_card_ratio: float
    cost_deviation: float
    dimension_scores: dict = Field(default_factory=dict)
    dim_details: dict = Field(default_factory=dict)
    match_details: list = Field(default_factory=list)  # 逐合同匹配明细（match_status / invoice_no / diff_amount 等）
    recommendations: dict = Field(default_factory=dict)
    business_narrative: str
    technical_summary: dict
    assessment_date: datetime


class RiskSnapshotResponse(BaseModel):
    """风险快照（只读，从已落库数据构建，含完整展示字段）"""
    risk_assessment_id: str
    enterprise_id: str
    overall_risk_level: str
    overall_risk_score: float
    four_flow_match_score: float
    private_card_ratio: float
    cost_deviation: float
    dimension_scores: dict = Field(default_factory=dict)
    dim_details: dict = Field(default_factory=dict)
    match_details: list = Field(default_factory=list)  # 逐合同匹配明细（match_status / invoice_no / diff_amount 等）
    recommendations: dict = Field(default_factory=dict)
    business_narrative: str = ""
    technical_summary: dict = Field(default_factory=dict)
    assessment_date: datetime


class RiskAssessmentResponse(BaseModel):
    id: str
    enterprise_id: str
    assessment_date: datetime
    overall_risk_level: str
    overall_risk_score: float
    four_flow_match_score: float
    private_card_ratio: float
    cost_deviation: float
    risk_details: dict
    recommendations: dict

    model_config = {"from_attributes": True}


class RiskAssessmentHistoryResponse(BaseModel):
    assessments: list[RiskAssessmentResponse]
    total: int
