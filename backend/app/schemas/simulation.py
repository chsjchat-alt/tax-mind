"""风险模拟 + 案例库 API Schemas"""
from pydantic import BaseModel, Field


class SimulationRequest(BaseModel):
    """风险模拟请求"""
    monthly_hidden_revenue: float = Field(default=0, ge=0, description="月均隐匿收入")
    comprehensive_tax_rate: float = Field(default=0.06, ge=0, le=1, description="综合税率")
    remediation_cost: float = Field(default=0, ge=0, description="合规整改成本")


class TimePointResponse(BaseModel):
    """单时间节点结果"""
    period: str
    months_elapsed: int
    path_a_cost: float
    path_b_cost: float
    audit_probability: float
    expected_penalty: float
    expected_late_fee: float
    cost_difference: float
    total_hidden_tax: float = 0.0


class ThirdPartyConsequenceResponse(BaseModel):
    """第三方后果关联"""
    bidding_restriction_days: int = 0
    bidding_restriction_detail: str = ""
    bank_credit_restriction_days: int = 0
    bank_credit_restriction_detail: str = ""
    government_subsidy_risk: str = ""
    blacklist_risk: str = ""
    social_credit_impact: str = ""


class PeerPressureResponse(BaseModel):
    """同行对比压力推送"""
    industry: str = ""
    peer_cases_count: int = 0
    peer_cases_detail: list[dict] = Field(default_factory=list)
    penalty_distribution: dict = Field(default_factory=dict)
    peer_compliance_rate: float = 0.0
    pressure_message: str = ""


class OfficialNoticeResponse(BaseModel):
    """模拟官方文书预览"""
    document_type: str = "第三方风险提示"
    document_title: str = ""
    document_number: str = ""
    issuing_body: str = ""
    enterprise_name: str = ""
    credit_code: str = ""
    risk_findings: list[str] = Field(default_factory=list)
    potential_consequences: list[str] = Field(default_factory=list)
    compliance_deadline: str = ""
    disclaimer: str = ""
    full_text: str = ""


class SimulationResponse(BaseModel):
    """风险模拟结果"""
    time_points: list[TimePointResponse]
    recommendation: str
    loss_frame_message: str
    technical_summary: dict
    case_references: list[str]
    effective_risk_level: str = "low"
    # ── Budge 升级：损失具象化增强 ──
    third_party_consequences: ThirdPartyConsequenceResponse | None = None
    peer_pressure: PeerPressureResponse | None = None
    official_notice: OfficialNoticeResponse | None = None


class CaseStudyResponse(BaseModel):
    case_id: str
    industry: str
    risk_level: str
    title: str
    summary: str
    key_findings: list
    outcome: str


class CaseStudiesResponse(BaseModel):
    cases: list[CaseStudyResponse]
    total: int
