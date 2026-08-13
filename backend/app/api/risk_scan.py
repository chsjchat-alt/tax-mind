"""
风险扫描 API

POST /api/v1/enterprises/{id}/risk-scan               执行风险扫描
GET  /api/v1/enterprises/{id}/risk-assessments         获取风险评估历史
GET  /api/v1/enterprises/{id}/risk-assessments/latest  获取最新风险评估
GET  /api/v1/risk-assessments/{id}                     获取风险评估详情
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db, success_response, error_response,
    require_viewer, require_auditor, get_enterprise_or_403,
)
from app.core.cache import risk_scan_cache
from app.core.risk_engine import assess_enterprise_risk
from app.core.four_flow_match import calculate_four_flow_match
from app.models.user import User
from app.schemas.risk_scan import (
    RiskScanResponse, RiskSnapshotResponse, RiskAssessmentResponse,
)
from app.services.risk_service import RiskScanService

router = APIRouter(tags=["风险扫描"])


@router.post("/enterprises/{enterprise_id}/risk-scan")
async def perform_risk_scan(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auditor),
):
    """执行风险扫描"""
    ent_id = str(enterprise_id)

    # 0. 租户隔离校验（先于缓存读取，避免跨租户命中缓存泄露数据）
    await get_enterprise_or_403(ent_id, current_user, db)

    # 1. 检查缓存（10分钟内重复扫描直接返回，避免重复计算）
    cache_key = f"scan:{ent_id}"
    cached_result = await risk_scan_cache.get(cache_key)
    if cached_result is not None:
        return success_response(cached_result)

    # 2. 加载企业数据
    ent, txs, invs, cts, decs = await RiskScanService.load_enterprise_data(db, ent_id, current_user.tenant_id)
    if not ent:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 2. 构建风险输入
    risk_input, ct_records, inv_records, bk_records = \
        RiskScanService.build_risk_input(ent, txs, invs, cts, decs)

    # 3. 补充财务数据
    await RiskScanService.enrich_with_financials(db, ent_id, risk_input)

    # 4. 执行风险扫描
    risk_result = assess_enterprise_risk(
        risk_input,
        contracts=ct_records,
        invoices=inv_records,
        bank_transactions=bk_records,
        has_tax_preference=ent.is_small_micro or ent.is_high_tech,
    )

    # 5. 四流匹配
    ffm_result = calculate_four_flow_match(ct_records, inv_records, bk_records)

    # 6. 持久化
    assessment = await RiskScanService.save_assessment(
        db, ent_id, risk_result, ffm_result,
        risk_input=risk_input, transactions=txs,
    )

    # 7. 构建响应
    total_rev = float(risk_input.total_revenue)
    private_ratio = (
        float(risk_input.total_private_card_amount) / total_rev
        if total_rev > 0 else 0
    )
    cost_dev = (
        float(risk_input.actual_cost_rate) - float(risk_input.cost_rate_industry)
        if float(risk_input.actual_cost_rate) > 0 else 0
    )

    response_data = RiskScanResponse(
        risk_assessment_id=assessment.id,
        enterprise_id=ent_id,
        overall_risk_level=risk_result.overall_risk_level,
        overall_risk_score=risk_result.overall_risk_score,
        four_flow_match_score=ffm_result.overall_score,
        private_card_ratio=round(private_ratio, 4),
        cost_deviation=cost_dev,
        dimension_scores=risk_result.dimension_scores,
        dim_details=risk_result.dim_details,
        match_details=ffm_result.details,
        recommendations={"items": risk_result.recommendations},
        business_narrative=risk_result.business_narrative,
        technical_summary=risk_result.technical_summary,
        assessment_date=assessment.assessment_date,
    ).model_dump()

    # 写入缓存
    await risk_scan_cache.set(cache_key, response_data)
    return success_response(response_data)


@router.get("/enterprises/{enterprise_id}/risk-assessments")
async def list_risk_assessments(
    enterprise_id: UUID,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """获取风险评估历史"""
    # 租户隔离校验
    await get_enterprise_or_403(str(enterprise_id), current_user, db)

    assessments, total = await RiskScanService.list_assessments(
        db, str(enterprise_id), limit, offset
    )

    return success_response({
        "assessments": [
            RiskAssessmentResponse.model_validate(a).model_dump()
            for a in assessments
        ],
        "total": total,
    })


@router.get("/enterprises/{enterprise_id}/risk-assessments/latest")
async def get_latest_risk_assessment(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """获取最新风险评估快照（只读，从已落库数据构建完整展示字段）"""
    # 租户隔离校验
    await get_enterprise_or_403(str(enterprise_id), current_user, db)

    assessment = await RiskScanService.get_latest_assessment(
        db, str(enterprise_id)
    )

    if not assessment:
        return error_response(40001, "暂无风险评估记录")

    snapshot = RiskSnapshotResponse(
        **RiskScanService.build_snapshot_from_assessment(assessment)
    )
    return success_response(snapshot.model_dump())


@router.get("/risk-assessments/{assessment_id}")
async def get_risk_assessment_detail(
    assessment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """获取风险评估详情"""
    assessment = await RiskScanService.get_assessment_by_id(
        db, str(assessment_id)
    )

    if not assessment:
        return error_response(40001, f"风险评估不存在: {assessment_id}")

    # 租户隔离校验：评估所属企业必须属于当前用户租户
    await get_enterprise_or_403(str(assessment.enterprise_id), current_user, db)

    return success_response(
        RiskAssessmentResponse.model_validate(assessment).model_dump()
    )
