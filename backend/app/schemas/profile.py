"""心理画像 API Schemas"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    """心理画像结果"""
    profile_id: UUID
    enterprise_id: UUID
    assessment_date: datetime
    control_desire_score: int
    loss_aversion_score: int
    optimism_bias_score: int
    control_illusion_score: int
    short_termism_score: int
    defensiveness_score: int
    deviation_index: float
    dominant_biases: list
    intervention_strategy: dict
    business_narrative: str
    technical_summary: dict
    peer_average: dict
    compliance_risk_level: Optional[str] = None


class ProfileHistoryItem(BaseModel):
    id: UUID
    enterprise_id: UUID
    assessment_date: datetime
    deviation_index: float
    dominant_biases: list

    model_config = {"from_attributes": True}


class ProfileHistoryResponse(BaseModel):
    profiles: list[ProfileHistoryItem]
    total: int
