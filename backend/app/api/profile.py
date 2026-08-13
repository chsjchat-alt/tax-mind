"""
心理画像 API

POST /api/v1/enterprises/{id}/profile             生成心理画像
GET  /api/v1/enterprises/{id}/profiles            获取心理画像历史
GET  /api/v1/enterprises/{id}/profiles/latest     获取最新心理画像
"""
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db, success_response, error_response,
    require_viewer, require_auditor, get_enterprise_or_403,
)
from app.models.enterprise import Enterprise
from app.models.bank_transaction import BankTransaction
from app.models.tax_declaration import TaxDeclaration
from app.models.psychological_profile import PsychologicalProfile
from app.models.risk_assessment import RiskAssessment
from app.models.remediation_task import RemediationTask, TaskStatus
from app.core.profile_engine import calculate_psychological_profile, BehavioralData, BIAS_CN
from app.core.four_flow_match import calculate_four_flow_match
from app.core.compliance_adjustment import compute_compliance_adjusted_risk
from app.models.user import User
from app.schemas.profile import ProfileResponse, ProfileHistoryResponse

router = APIRouter(tags=["心理画像"])

# ── 加载行业基准数据（用于税负偏差计算） ──
_BENCHMARKS_PATH = Path(__file__).resolve().parent.parent / "data" / "industry_benchmarks.json"
try:
    with open(_BENCHMARKS_PATH, "r", encoding="utf-8") as _f:
        _INDUSTRY_BENCHMARKS = json.load(_f)
except (FileNotFoundError, json.JSONDecodeError, OSError) as _e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.warning("行业基准数据加载失败 (%s): %s，税负偏差计算将跳过", _BENCHMARKS_PATH, _e)
    _INDUSTRY_BENCHMARKS = {}


def _compute_tax_burden_deviation(enterprise: Enterprise) -> float:
    """根据企业所属行业基准和申报税负率计算税负偏差（百分点）"""
    if not enterprise.tax_rate_claimed or not enterprise.industry:
        return 0.0

    claimed_rate = float(enterprise.tax_rate_claimed)
    benchmarks = _INDUSTRY_BENCHMARKS.get("benchmarks", {})

    # 精确匹配行业基准
    industry_data = benchmarks.get(enterprise.industry)

    if not industry_data:
        return 0.0

    industry_mean = industry_data.get("tax_burden_rate_mean")
    if industry_mean is None:
        return 0.0

    # 偏差 = 行业均值 - 企业申报率（正数表示企业税负低于行业均值，即偏低）
    return round(float(industry_mean) - claimed_rate, 2)


async def _build_behavioral_data(
    enterprise: Enterprise,
    db: AsyncSession,
) -> BehavioralData:
    """从企业数据构建行为数据输入（并发执行6项独立查询）"""
    eid = enterprise.id

    async def _fetch_transactions():
        result = await db.execute(
            select(BankTransaction).where(BankTransaction.enterprise_id == eid)
        )
        return result.scalars().all()

    async def _fetch_risk_count():
        result = await db.execute(select(func.count()).select_from(
            select(RiskAssessment).where(RiskAssessment.enterprise_id == eid).subquery()
        ))
        return result.scalar() or 0

    async def _fetch_high_count():
        result = await db.execute(
            select(func.count()).select_from(
                select(RiskAssessment).where(
                    RiskAssessment.enterprise_id == eid,
                    RiskAssessment.overall_risk_level == "high",
                ).subquery()
            )
        )
        return result.scalar() or 0

    async def _fetch_recent_risks():
        result = await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.enterprise_id == eid
            ).order_by(RiskAssessment.assessment_date.desc()).limit(4)
        )
        return result.scalars().all()

    async def _fetch_latest_risk():
        result = await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.enterprise_id == eid
            ).order_by(RiskAssessment.assessment_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def _fetch_declarations():
        result = await db.execute(
            select(TaxDeclaration).where(TaxDeclaration.enterprise_id == eid)
        )
        return result.scalars().all()

    async def _fetch_remediation_rate():
        """整改任务完成率 = 已完成任务数 / 总任务数 * 100（无任务返回 0）"""
        total_result = await db.execute(
            select(func.count()).select_from(
                select(RemediationTask).where(RemediationTask.enterprise_id == eid).subquery()
            )
        )
        total_tasks = total_result.scalar() or 0
        if total_tasks == 0:
            return 0.0
        completed_result = await db.execute(
            select(func.count()).select_from(
                select(RemediationTask).where(
                    RemediationTask.enterprise_id == eid,
                    RemediationTask.status == TaskStatus.COMPLETED,
                ).subquery()
            )
        )
        completed_tasks = completed_result.scalar() or 0
        return round(completed_tasks / total_tasks * 100, 2)

    # 并发执行所有独立查询
    (
        transactions,
        risk_count,
        high_count,
        recent_risks,
        latest_risk,
        declarations,
        remediation_rate,
    ) = await asyncio.gather(
        _fetch_transactions(),
        _fetch_risk_count(),
        _fetch_high_count(),
        _fetch_recent_risks(),
        _fetch_latest_risk(),
        _fetch_declarations(),
        _fetch_remediation_rate(),
    )

    # ── 计算私卡占比 ──
    total_inflow = Decimal("0")
    private_inflow = Decimal("0")
    for tx in transactions:
        amt = Decimal(str(tx.amount))
        if tx.direction == "inflow":
            total_inflow += amt
            if tx.account_type == "personal":
                private_inflow += amt
    private_ratio = float(private_inflow / total_inflow) if total_inflow > 0 else 0.0

    # ── 税负率偏离 ──
    tax_burden_deviation = _compute_tax_burden_deviation(enterprise)

    # ── 高风险复发率 ──
    risk_recurrence = high_count / risk_count if risk_count > 0 else 0.0

    # ── 连续高风险期数 ──
    consecutive = 0
    if high_count > 0:
        for r in recent_risks:
            if r.overall_risk_level.value == "high":
                consecutive += 1

    # ── 四流匹配度 ──
    four_flow_score = latest_risk.four_flow_match_score if latest_risk else 100.0

    # ── 未申报收入占比 ──
    total_declared = sum(Decimal(str(d.declared_revenue)) for d in declarations)
    total_revenue = Decimal(str(enterprise.revenue_annual or 0))
    undeclared_ratio = float(1 - total_declared / total_revenue) if total_revenue > 0 else 0.0
    undeclared_ratio = max(0.0, undeclared_ratio)

    return BehavioralData(
        private_card_ratio=private_ratio,
        tax_burden_deviation=tax_burden_deviation,
        historical_risk_count=risk_count,
        risk_recurrence_rate=risk_recurrence,
        four_flow_match_score=four_flow_score,
        undeclared_revenue_ratio=undeclared_ratio,
        remediation_completion_rate=remediation_rate,
        consecutive_high_risk_periods=consecutive,
        is_high_tech=enterprise.is_high_tech,
        is_small_micro=enterprise.is_small_micro,
        revenue_annual=enterprise.revenue_annual or 0,
    )


@router.post("/enterprises/{enterprise_id}/profile")
async def generate_profile(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auditor),
):
    """生成心理画像"""
    ent_id = str(enterprise_id)

    # 租户隔离校验
    enterprise = await get_enterprise_or_403(ent_id, current_user, db)

    behavioral = await _build_behavioral_data(enterprise, db)
    profile_result = calculate_psychological_profile(
        behavioral,
        industry=enterprise.industry or "",
        revenue_annual=float(enterprise.revenue_annual or 0),
    )

    # 合规调整风险评分
    compliance = await compute_compliance_adjusted_risk(db=db, enterprise_id=ent_id)
    adjusted_deviation = round(
        profile_result.deviation_index * (1 - compliance["reduction_pct"] * 0.5), 2
    )
    compliance_risk_level = compliance["adjusted_level"]

    # 保存到数据库
    profile = PsychologicalProfile(
        enterprise_id=ent_id,
        assessment_date=datetime.now(timezone.utc),
        control_desire_score=profile_result.control_desire_score,
        loss_aversion_score=profile_result.loss_aversion_score,
        optimism_bias_score=profile_result.optimism_bias_score,
        control_illusion_score=profile_result.control_illusion_score,
        short_termism_score=profile_result.short_termism_score,
        defensiveness_score=profile_result.defensiveness_score,
        deviation_index=profile_result.deviation_index,
        dominant_biases=[BIAS_CN.get(b, b) for b in profile_result.dominant_biases],
        intervention_strategy={BIAS_CN.get(k, k): v for k, v in profile_result.intervention_strategy.items()},
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)

    return success_response(ProfileResponse(
        profile_id=profile.id,
        enterprise_id=enterprise_id,
        assessment_date=profile.assessment_date,
        control_desire_score=profile_result.control_desire_score,
        loss_aversion_score=profile_result.loss_aversion_score,
        optimism_bias_score=profile_result.optimism_bias_score,
        control_illusion_score=profile_result.control_illusion_score,
        short_termism_score=profile_result.short_termism_score,
        defensiveness_score=profile_result.defensiveness_score,
        deviation_index=adjusted_deviation,
        dominant_biases=[BIAS_CN.get(b, b) for b in profile_result.dominant_biases],
        intervention_strategy={BIAS_CN.get(k, k): v for k, v in profile_result.intervention_strategy.items()},
        business_narrative=profile_result.business_narrative,
        technical_summary=profile_result.technical_summary,
        peer_average=profile_result.peer_average,
        compliance_risk_level=compliance_risk_level,
    ).model_dump())


@router.get("/enterprises/{enterprise_id}/profiles")
async def list_profiles(
    enterprise_id: UUID,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """获取心理画像历史"""
    ent_id = str(enterprise_id)

    # 租户隔离校验
    await get_enterprise_or_403(ent_id, current_user, db)

    query = select(PsychologicalProfile).where(
        PsychologicalProfile.enterprise_id == ent_id
    ).order_by(PsychologicalProfile.assessment_date.desc())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    profiles = result.scalars().all()

    return success_response({
        "profiles": [
            {
                "id": str(p.id),
                "enterprise_id": str(p.enterprise_id),
                "assessment_date": p.assessment_date.isoformat(),
                "deviation_index": float(p.deviation_index),
                "dominant_biases": p.dominant_biases,
            }
            for p in profiles
        ],
        "total": total,
    })


@router.get("/enterprises/{enterprise_id}/profiles/latest")
async def get_latest_profile(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """获取最新心理画像"""
    ent_id = str(enterprise_id)

    # 租户隔离校验（同时取得企业信息用于行业×规模基准匹配）
    enterprise = await get_enterprise_or_403(ent_id, current_user, db)

    result = await db.execute(
        select(PsychologicalProfile).where(
            PsychologicalProfile.enterprise_id == ent_id
        ).order_by(PsychologicalProfile.assessment_date.desc()).limit(1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return error_response(40001, "暂无心理画像记录")

    # 动态计算同行基准
    from app.core.profile_engine import lookup_peer_average
    peer_avg = lookup_peer_average(
        industry=enterprise.industry or "" if enterprise else "",
        revenue_annual=float(enterprise.revenue_annual or 0) if enterprise else 0.0,
    )

    # 合规调整风险评分
    compliance = await compute_compliance_adjusted_risk(db=db, enterprise_id=ent_id)
    adjusted_deviation = round(
        float(profile.deviation_index) * (1 - compliance["reduction_pct"] * 0.5), 2
    )
    compliance_risk_level = compliance["adjusted_level"]

    return success_response({
        "id": str(profile.id),
        "enterprise_id": str(profile.enterprise_id),
        "assessment_date": profile.assessment_date.isoformat(),
        "control_desire_score": profile.control_desire_score,
        "loss_aversion_score": profile.loss_aversion_score,
        "optimism_bias_score": profile.optimism_bias_score,
        "control_illusion_score": profile.control_illusion_score,
        "short_termism_score": profile.short_termism_score,
        "defensiveness_score": profile.defensiveness_score,
        "deviation_index": adjusted_deviation,
        "dominant_biases": profile.dominant_biases,
        "intervention_strategy": profile.intervention_strategy,
        "peer_average": peer_avg,
        "compliance_risk_level": compliance_risk_level,
    })
