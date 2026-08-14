"""
企业管理 API（多租户隔离版）

GET    /api/v1/enterprises              获取企业列表（仅当前租户）
GET    /api/v1/enterprises/{id}         获取企业详情（租户隔离校验）
POST   /api/v1/enterprises              创建企业（自动归属当前租户）
PUT    /api/v1/enterprises/{id}         更新企业信息（租户隔离校验）
DELETE /api/v1/enterprises/{id}         删除企业（租户隔离校验）
"""
import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db, success_response, error_response,
    require_viewer, require_admin,
    get_current_tenant_id,
)
from app.models.enterprise import Enterprise
from app.models.bank_transaction import BankTransaction
from app.models.user import User
from app.models.invoice import Invoice
from app.models.tax_declaration import TaxDeclaration
from app.models.contract import Contract
from app.models.financial_statement import FinancialStatement
from app.models.risk_assessment import RiskAssessment
from app.schemas.enterprise import (
    EnterpriseCreate, EnterpriseUpdate, EnterpriseResponse,
    EnterpriseSummary, EnterpriseDetailResponse,
)
from app.core.compliance_adjustment import (
    compute_compliance_adjusted_risk,
    compute_compliance_adjusted_risks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enterprises", tags=["企业管理"])


@router.get("")
async def list_enterprises(
    industry: str | None = None,
    risk_level: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取企业列表（仅当前租户），支持按行业/风险等级筛选"""
    query = select(Enterprise).where(
        Enterprise.tenant_id == tenant_id,
    ).order_by(Enterprise.created_at.desc())

    if industry:
        query = query.where(Enterprise.industry == industry)
    if risk_level:
        query = query.where(Enterprise.risk_level == risk_level)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    enterprises = result.scalars().all()

    summaries = [
        EnterpriseSummary.model_validate(e) for e in enterprises
    ]

    # ── 合规调整：批量注入联动风险等级（一次 IN 查询，消除 N+1）──
    if summaries:
        try:
            ids = [str(s.id) for s in summaries]
            adjusted_map = await compute_compliance_adjusted_risks(db, ids)
            for summary in summaries:
                adj = adjusted_map.get(str(summary.id))
                if adj:
                    summary.risk_level = adj["adjusted_level"]
        except Exception as exc:
            logger.warning("企业列表合规调整批量计算失败: %s", exc)

    return success_response({
        "enterprises": summaries,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.get("/{enterprise_id}")
async def get_enterprise(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取企业详情（租户隔离校验）"""
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == str(enterprise_id),
            Enterprise.tenant_id == tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()

    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 统计数据量
    eid = str(enterprise_id)
    models = [
        (BankTransaction, "bank_transactions"),
        (Invoice, "invoices"),
        (TaxDeclaration, "tax_declarations"),
        (Contract, "contracts"),
        (FinancialStatement, "financial_statements"),
        (RiskAssessment, "risk_assessments"),
    ]

    async def _count(model):
        # 单表统计失败不拖垮详情接口：生产库若存在列/表漂移（create_all 不补列），
        # 该表计数降级为 0 并记录日志，其余数据正常返回
        try:
            result = await db.execute(
                select(func.count()).select_from(
                    select(model).where(model.enterprise_id == eid).subquery()
                )
            )
            return result.scalar() or 0
        except Exception as exc:
            logger.warning(
                "企业详情统计失败 model=%s enterprise=%s: %s",
                model.__name__, enterprise_id, exc,
            )
            return 0

    counts = await asyncio.gather(*(_count(m) for m, _ in models))
    stats = {label: cnt for (_, label), cnt in zip(models, counts)}

    # ── 合规调整 → 注入联动风险等级 ──
    compliance_adj = None
    try:
        compliance_adj = await compute_compliance_adjusted_risk(
            db, str(enterprise_id),
            base_score=None,
        )
    except Exception as exc:
        logger.warning("企业详情合规调整计算失败 enterprise=%s: %s", enterprise_id, exc)

    detail = EnterpriseDetailResponse(
        enterprise=EnterpriseResponse.model_validate(enterprise),
        statistics=stats,
    ).model_dump()
    if compliance_adj:
        detail["compliance"] = compliance_adj
        detail["enterprise"]["risk_level"] = compliance_adj["adjusted_level"]

    return success_response(detail)


@router.post("", status_code=201)
async def create_enterprise(
    data: EnterpriseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建企业（自动归属当前用户的租户）"""
    # 检查同一租户下统一社会信用代码是否已存在
    existing = await db.execute(
        select(Enterprise).where(
            Enterprise.credit_code == data.credit_code,
            Enterprise.tenant_id == current_user.tenant_id,
        )
    )
    if existing.scalar_one_or_none():
        return error_response(40002, f"统一社会信用代码已存在: {data.credit_code}")

    enterprise = Enterprise(
        tenant_id=current_user.tenant_id,
        **data.model_dump(),
    )
    db.add(enterprise)
    await db.flush()
    await db.refresh(enterprise)

    return success_response(
        EnterpriseResponse.model_validate(enterprise).model_dump(),
        message="企业创建成功",
    )


@router.put("/{enterprise_id}")
async def update_enterprise(
    enterprise_id: UUID,
    data: EnterpriseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新企业信息（租户隔离校验）"""
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == str(enterprise_id),
            Enterprise.tenant_id == current_user.tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()

    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(enterprise, key, value)

    # 一票否决输入变化（纳税信用等级 / 涉税犯罪标志）→ 失效风险扫描缓存，
    # 确保下次扫描按新口径重新计算（2025 年第 12 号直接判 D 语义）
    if {"tax_credit_level", "tax_crime_convicted"} & set(update_data.keys()):
        from app.core.cache import risk_scan_cache
        await risk_scan_cache.invalidate(f"scan:{str(enterprise_id)}")

    await db.flush()
    await db.refresh(enterprise)

    return success_response(
        EnterpriseResponse.model_validate(enterprise).model_dump(),
        message="企业信息更新成功",
    )


@router.delete("/{enterprise_id}")
async def delete_enterprise(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """删除企业（租户隔离校验 + 级联删除关联数据）"""
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == str(enterprise_id),
            Enterprise.tenant_id == current_user.tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()

    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    await db.delete(enterprise)
    await db.flush()

    return success_response(None, message="企业已删除")
