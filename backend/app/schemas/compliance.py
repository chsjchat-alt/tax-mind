"""合规导航 API Schemas"""
from pydantic import BaseModel, Field


class TaxPreferenceResponse(BaseModel):
    """税收优惠校验结果"""
    is_small_micro: bool
    small_micro_eligible: bool
    small_micro_conditions: dict
    is_high_tech: bool
    high_tech_risk: str | None = None
    current_status: str
    industry_preferences: list
    recommendations: list
    business_narrative: str
    technical_summary: dict
    compliance_risk_level: str | None = None


class InterventionLayerResponse(BaseModel):
    layer: int
    name: str
    theory: str
    visual_type: str
    content: str


class InterventionResponse(BaseModel):
    """心理干预策略"""
    layers: list[InterventionLayerResponse]
    business_narrative: str
    technical_summary: dict | None = None
    priority_bias: str | None = None
    priority_order: list[int] = []
    compliance_risk_level: str | None = None
