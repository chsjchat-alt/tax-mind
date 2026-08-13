"""
数据接入 API

GET/POST /api/v1/enterprises/{id}/bank-statements      银行流水
GET/POST /api/v1/enterprises/{id}/invoices             发票数据
GET      /api/v1/enterprises/{id}/tax-declarations     纳税申报
GET      /api/v1/enterprises/{id}/contracts            合同台账
GET      /api/v1/enterprises/{id}/financial-statements 财务报表
POST     /api/v1/enterprises/{id}/load-mock-data       一键加载模拟数据
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, success_response, error_response, require_viewer, require_admin, get_current_tenant_id
from app.core.cache import invalidate_enterprise_caches
from app.models.bank_transaction import BankTransaction
from app.models.invoice import Invoice
from app.models.tax_declaration import TaxDeclaration
from app.models.contract import Contract
from app.models.financial_statement import FinancialStatement
from app.models.enterprise import Enterprise
from app.models.user import User
from app.schemas.data_ingestion import (
    BankTransactionResponse, BankTransactionFilter,
    InvoiceResponse, InvoiceFilter,
    TaxDeclarationResponse, ContractResponse,
    FinancialStatementResponse, MockDataLoadResponse,
)

router = APIRouter(prefix="/enterprises/{enterprise_id}", tags=["数据接入"])


# ── 银行流水 ──
@router.get("/bank-statements")
async def list_bank_transactions(
    enterprise_id: str,
    account_type: str | None = Query(None, description="corporate/personal"),
    direction: str | None = Query(None, description="inflow/outflow"),
    start_date: str | None = Query(None, description="开始日期"),
    end_date: str | None = Query(None, description="结束日期"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取银行流水列表"""
    # 校验企业归属租户
    ent_result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not ent_result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    query = select(BankTransaction).where(
        BankTransaction.enterprise_id == enterprise_id
    ).order_by(BankTransaction.transaction_date.desc())

    if account_type:
        query = query.where(BankTransaction.account_type == account_type)
    if direction:
        query = query.where(BankTransaction.direction == direction)
    if start_date:
        query = query.where(BankTransaction.transaction_date >= start_date)
    if end_date:
        query = query.where(BankTransaction.transaction_date <= end_date)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    transactions = result.scalars().all()

    return success_response({
        "transactions": [
            BankTransactionResponse.model_validate(tx).model_dump()
            for tx in transactions
        ],
        "total": total,
    })


@router.post("/bank-statements")
async def import_bank_statements(
    enterprise_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """导入银行流水（模拟）——原型阶段返回成功提示"""
    # 校验企业归属租户
    ent_result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not ent_result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    return success_response(
        {"enterprise_id": str(enterprise_id), "imported": 0},
        message="模拟导入成功（原型阶段，请使用 load-mock-data 接口加载完整模拟数据）",
    )


# ── 发票 ──
@router.get("/invoices")
async def list_invoices(
    enterprise_id: str,
    invoice_type: str | None = Query(None, description="input/output"),
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取发票数据列表"""
    # 校验企业归属租户
    ent_result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not ent_result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    query = select(Invoice).where(
        Invoice.enterprise_id == enterprise_id
    ).order_by(Invoice.invoice_date.desc())

    if invoice_type:
        query = query.where(Invoice.invoice_type == invoice_type)
    if start_date:
        query = query.where(Invoice.invoice_date >= start_date)
    if end_date:
        query = query.where(Invoice.invoice_date <= end_date)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    invoices = result.scalars().all()

    return success_response({
        "invoices": [
            InvoiceResponse.model_validate(inv).model_dump()
            for inv in invoices
        ],
        "total": total,
    })


@router.post("/invoices")
async def import_invoices(
    enterprise_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """导入发票数据（模拟）"""
    # 校验企业归属租户
    ent_result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not ent_result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    return success_response(
        {"enterprise_id": str(enterprise_id), "imported": 0},
        message="模拟导入成功（原型阶段，请使用 load-mock-data 接口加载完整模拟数据）",
    )


# ── 纳税申报 ──
@router.get("/tax-declarations")
async def list_tax_declarations(
    enterprise_id: str,
    tax_type: str | None = Query(None, description="vat/income_tax/personal_income_tax"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取纳税申报列表"""
    # 校验企业归属租户
    ent_result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not ent_result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    query = select(TaxDeclaration).where(
        TaxDeclaration.enterprise_id == enterprise_id
    ).order_by(TaxDeclaration.period.desc())

    if tax_type:
        query = query.where(TaxDeclaration.tax_type == tax_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    declarations = result.scalars().all()

    return success_response({
        "declarations": [
            TaxDeclarationResponse.model_validate(d).model_dump()
            for d in declarations
        ],
        "total": total,
    })


# ── 合同 ──
@router.get("/contracts")
async def list_contracts(
    enterprise_id: str,
    contract_type: str | None = Query(None, description="sales/purchase"),
    status: str | None = Query(None, description="履约状态"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取合同台账列表"""
    # 校验企业归属租户
    ent_result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not ent_result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    query = select(Contract).where(
        Contract.enterprise_id == enterprise_id
    ).order_by(Contract.signing_date.desc())

    if contract_type:
        query = query.where(Contract.contract_type == contract_type)
    if status:
        query = query.where(Contract.execution_status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    contracts = result.scalars().all()

    return success_response({
        "contracts": [
            ContractResponse.model_validate(c).model_dump()
            for c in contracts
        ],
        "total": total,
    })


# ── 财务报表 ──
@router.get("/financial-statements")
async def list_financial_statements(
    enterprise_id: str,
    statement_type: str | None = Query(
        None, description="balance_sheet/income_statement/cash_flow"
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取财务报表列表"""
    # 校验企业归属租户
    ent_result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not ent_result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    query = select(FinancialStatement).where(
        FinancialStatement.enterprise_id == enterprise_id
    ).order_by(FinancialStatement.period.desc())

    if statement_type:
        query = query.where(FinancialStatement.statement_type == statement_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    stmts = result.scalars().all()

    return success_response({
        "statements": [
            FinancialStatementResponse.model_validate(s).model_dump()
            for s in stmts
        ],
        "total": total,
    })


# ── 一键加载模拟数据 ──
@router.post("/load-mock-data")
async def load_mock_data(
    enterprise_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """一键加载模拟数据到指定企业"""
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()

    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 根据企业行业推断企业类型
    industry_to_type = {
        "批发零售": "A",
        "制造": "B",
        "建筑": "C",
        "电商": "D",
        "餐饮服务": "E",
    }
    enterprise_type = industry_to_type.get(str(enterprise.industry), "A")

    from app.data.mock_data_generator import load_mock_data_to_db
    await load_mock_data_to_db(enterprise_type, db, existing_enterprise_id=enterprise_id)

    # 清除该企业的风险扫描缓存（数据已变更）
    invalidate_enterprise_caches(enterprise_id)

    return success_response(
        {"enterprise_id": str(enterprise_id), "enterprise_name": enterprise.name},
        message=f"模拟数据加载成功（企业类型 {enterprise_type}）",
    )
