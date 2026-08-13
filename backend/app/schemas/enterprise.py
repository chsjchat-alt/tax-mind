"""企业管理 API Schemas"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EnterpriseCreate(BaseModel):
    """创建企业请求"""
    name: str = Field(..., min_length=1, max_length=200, description="企业名称")
    credit_code: str = Field(..., min_length=15, max_length=18, description="统一社会信用代码")
    industry: str = Field(..., description="行业类型（批发零售/制造/建筑/电商/餐饮服务）")
    revenue_annual: float = Field(default=0, ge=0, description="年营收")
    employee_count: int = Field(default=0, ge=0, description="员工人数")
    tax_rate_claimed: float = Field(default=0, ge=0, le=100, description="申报税负率(%)")
    cost_rate_claimed: float = Field(default=0, ge=0, le=200, description="申报成本费用率(%)")
    is_high_tech: bool = Field(default=False, description="是否高新技术企业")
    is_small_micro: bool = Field(default=True, description="是否小微企业")
    risk_level: str = Field(default="low", description="当前风险等级（low/medium/high）")


class EnterpriseUpdate(BaseModel):
    """更新企业请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    industry: Optional[str] = None
    revenue_annual: Optional[float] = Field(None, ge=0)
    employee_count: Optional[int] = Field(None, ge=0)
    tax_rate_claimed: Optional[float] = Field(None, ge=0, le=100)
    cost_rate_claimed: Optional[float] = Field(None, ge=0, le=200)
    is_high_tech: Optional[bool] = None
    is_small_micro: Optional[bool] = None
    risk_level: Optional[str] = None


class EnterpriseResponse(BaseModel):
    """企业信息响应"""
    id: UUID
    name: str
    credit_code: str
    industry: str
    revenue_annual: float
    employee_count: int
    tax_rate_claimed: float
    cost_rate_claimed: float
    is_high_tech: bool
    is_small_micro: bool
    risk_level: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnterpriseSummary(BaseModel):
    """企业列表摘要"""
    id: UUID
    name: str
    industry: str
    revenue_annual: float
    risk_level: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EnterpriseDetailResponse(BaseModel):
    """企业详情（含统计信息）"""
    enterprise: EnterpriseResponse
    statistics: dict = Field(default_factory=dict, description="数据统计")
