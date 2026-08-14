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
from typing import Any
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


def _count_findings(risk_details: Any) -> int:
    """统计风险明细中的正向发现数（正数数值键计为 1 个发现）。"""
    if not isinstance(risk_details, dict):
        return 0
    return sum(
        1 for v in risk_details.values() if isinstance(v, (int, float)) and v > 0
    )


async def _get_latest_risk_assessment(
    db: AsyncSession,
    enterprise_id: str,
) -> RiskAssessment | None:
    result = await db.execute(
        select(RiskAssessment)
        .where(RiskAssessment.enterprise_id == enterprise_id)
        .order_by(RiskAssessment.assessment_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


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
            # 批量加载各企业最新一次评估的发现数与原始分（一次查询，消除 N+1）
            findings_counts: dict[str, int] = {}
            base_scores: dict[str, float] = {}
            ra_result = await db.execute(
                select(RiskAssessment)
                .where(RiskAssessment.enterprise_id.in_(ids))
                .order_by(RiskAssessment.assessment_date.desc())
            )
            for ra in ra_result.scalars().all():
                if ra.enterprise_id not in findings_counts:
                    findings_counts[ra.enterprise_id] = _count_findings(ra.risk_details)
                    if ra.overall_risk_score is not None:
                        base_scores[ra.enterprise_id] = float(ra.overall_risk_score)
            adjusted_map = await compute_compliance_adjusted_risks(
                db, ids,
                compliance_findings_counts=findings_counts,
                base_scores=base_scores,
            )
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

    # ── 合规调整 → 注入联动风险等级（传入最新评估分与发现数，完全合规 LOW 全链路生效）──
    compliance_adj = None
    try:
        latest_risk = await _get_latest_risk_assessment(db, str(enterprise_id))
        compliance_adj = await compute_compliance_adjusted_risk(
            db, str(enterprise_id),
            base_score=(
                float(latest_risk.overall_risk_score)
                if latest_risk and latest_risk.overall_risk_score is not None
                else None
            ),
            compliance_findings_count=(
                _count_findings(latest_risk.risk_details) if latest_risk else None
            ),
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
