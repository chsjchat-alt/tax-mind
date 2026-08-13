"""数据接入 API Schemas"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── 银行流水 ──
class BankTransactionResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    transaction_date: date
    direction: str  # inflow / outflow
    amount: float
    account_type: str  # corporate / personal
    counterparty: str
    description: str
    is_declared: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BankTransactionFilter(BaseModel):
    account_type: Optional[str] = Field(None, description="公户corporate / 私卡personal")
    direction: Optional[str] = Field(None, description="inflow / outflow")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# ── 发票 ──
class InvoiceResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    invoice_no: str
    invoice_type: str
    invoice_date: date
    product_name: str
    tax_rate: float
    amount: float
    tax_amount: float
    total_amount: float
    buyer_name: str
    seller_name: str
    is_digital: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceFilter(BaseModel):
    invoice_type: Optional[str] = Field(None, description="input/output")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# ── 纳税申报 ──
class TaxDeclarationResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    tax_type: str
    period: str
    declared_revenue: float
    declared_tax: float
    actual_paid: float
    declaration_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 合同 ──
class ContractResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    contract_no: str
    contract_type: str
    counterparty: str
    contract_amount: float
    signing_date: date
    execution_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 财务报表 ──
class FinancialStatementResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    period: str
    statement_type: str
    total_assets: float
    total_liabilities: float
    total_revenue: float
    total_cost: float
    net_profit: float
    operating_cash_flow: float
    tax_burden_rate: float
    cost_rate: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 一键导入响应 ──
class MockDataLoadResponse(BaseModel):
    enterprise_id: UUID
    enterprise_name: str
    summary: dict
