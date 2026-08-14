"""
合规导航 API

GET  /api/v1/enterprises/{id}/tax-preference   税收优惠校验
GET  /api/v1/enterprises/{id}/intervention     获取心理干预策略
POST /api/v1/enterprises/{id}/nbt-intervention  获取NBT三层行为干预（LLM）
"""
import logging
import math
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    error_response,
    get_current_tenant_id,
    get_db,
    require_auditor,
    require_viewer,
    success_response,
)
from app.models.enterprise import Enterprise
from app.models.risk_assessment import RiskAssessment
from app.models.psychological_profile import PsychologicalProfile
from app.core.tax_preference import check_tax_preference, PreferenceCheckInput
from app.core.intervention import generate_intervention, InterventionInput
from app.core.compliance_adjustment import compute_compliance_adjusted_risk
from app.core.npt_dynamic_mix import compute_npt_mix
from app.core.trudge_toolbox import (
    generate_self_audit_report,
    simulate_installment_payment,
)
from app.core.profile_engine import BIAS_CN, lookup_peer_average
from app.models.user import User
from app.schemas.compliance import InterventionResponse, TaxPreferenceResponse
from app.services.llm_intervention_service import llm_intervention_service

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["合规导航"])

RISK_CATEGORY_MAPPING = {
    "private_card_ratio": "tax",
    "cost_deviation": "accounting",
    "tax_burden_deviation": "tax",
    "four_flow_mismatch": "invoice",
    "invoice_bank_mismatch": "invoice",
    "large_personal_transfer": "financial",
    "input_output_imbalance": "tax",
}

RISK_CATEGORY_NAME_MAPPING = {
    "private_card_ratio": "私卡收款",
    "cost_deviation": "成本偏离",
    "tax_burden_deviation": "税负率",
    "four_flow_mismatch": "四流匹配",
    "invoice_bank_mismatch": "票银匹配",
    "large_personal_transfer": "大额公转私",
    "input_output_imbalance": "进销项平衡",
}

ALLOWED_RISK_KEYS = frozenset(
    {
        "compound_penalty",
        "penalty",
        "total_unpaid_principal",
        "total_unpaid_tax",
        "total_late_fee",
        "total_daily_late_fee",
        "overall_risk_score",
        "overall_risk_level",
        "risk_factors",
    }
)
MAX_RISK_ITEMS = 20
MAX_RISK_DEPTH = 4
MAX_RISK_STRING_LENGTH = 200
MAX_RISK_KEY_LENGTH = 64


async def _get_enterprise(
    db: AsyncSession,
    enterprise_id: str,
    tenant_id: str,
) -> Enterprise | None:
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


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


async def _get_latest_profile(
    db: AsyncSession,
    enterprise_id: str,
) -> PsychologicalProfile | None:
    result = await db.execute(
        select(PsychologicalProfile)
        .where(PsychologicalProfile.enterprise_id == enterprise_id)
        .order_by(PsychologicalProfile.assessment_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_compliance_adjustment(
    db: AsyncSession,
    enterprise_id: str,
    *,
    base_score: float | None = None,
    compliance_findings_count: int | None = None,
) -> dict[str, Any] | None:
    try:
        return await compute_compliance_adjusted_risk(
            db=db,
            enterprise_id=enterprise_id,
            base_score=base_score,
            compliance_findings_count=compliance_findings_count,
        )
    except Exception:
        LOGGER.warning(
            "合规调整计算失败 enterprise_id=%s",
            enterprise_id[:8],
            exc_info=True,
        )
        return None


def _sanitize_risk_value(value: Any, *, depth: int = 0) -> Any | None:
    if depth > MAX_RISK_DEPTH or value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None

    if isinstance(value, str):
        cleaned = " ".join(value.split())
        if not cleaned:
            return None
        return cleaned[:MAX_RISK_STRING_LENGTH]

    if isinstance(value, list):
        sanitized_items = []
        for item in value[:MAX_RISK_ITEMS]:
            sanitized_item = _sanitize_risk_value(item, depth=depth + 1)
            if sanitized_item is not None:
                sanitized_items.append(sanitized_item)
        return sanitized_items

    if isinstance(value, dict):
        sanitized_mapping: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:MAX_RISK_ITEMS]:
            if not isinstance(raw_key, str):
                continue
            key = raw_key.strip()[:MAX_RISK_KEY_LENGTH]
            if not key:
                continue
            sanitized_item = _sanitize_risk_value(raw_value, depth=depth + 1)
            if sanitized_item is not None:
                sanitized_mapping[key] = sanitized_item
        return sanitized_mapping

    return None


def _sanitize_client_risk_data(risk_data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ALLOWED_RISK_KEYS:
        if key not in risk_data:
            continue
        sanitized_value = _sanitize_risk_value(risk_data[key])
        if sanitized_value is not None:
            sanitized[key] = sanitized_value
    return sanitized


def _extract_positive_risk_details(risk_details: Any) -> dict[str, float]:
    if not isinstance(risk_details, dict):
        return {}

    positive_details: dict[str, float] = {}
    for key, value in risk_details.items():
        if isinstance(value, (int, float)) and value > 0:
            positive_details[key] = float(value)
    return positive_details


def _count_findings(risk_details: Any) -> int:
    return len(_extract_positive_risk_details(risk_details))


def _derive_dominant_biases(
    profile: PsychologicalProfile,
    enterprise: Enterprise,
) -> list[str]:
    scores: dict[str, int | float] = {
        "control_desire": int(profile.control_desire_score or 0),
        "loss_aversion": int(profile.loss_aversion_score or 0),
        "optimism_bias": int(profile.optimism_bias_score or 0),
        "control_illusion": int(profile.control_illusion_score or 0),
        "short_termism": int(profile.short_termism_score or 0),
        "defensiveness": int(profile.defensiveness_score or 0),
    }

    zero_count = sum(1 for value in scores.values() if value == 0)
    if zero_count >= 3:
        peer_avg = lookup_peer_average(
            industry=str(enterprise.industry),
            revenue_annual=float(enterprise.revenue_annual or 0),
        )
        scores = {
            key: peer_avg.get(key, scores[key])
            for key in scores
        }

    sorted_biases = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    return [bias for bias, _ in sorted_biases[:2]]


def _build_self_audit_findings(risk_details: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for key, value in _extract_positive_risk_details(risk_details).items():
        findings.append(
            {
                "rule_key": key,
                "category": _find_category(key),
                "severity": _find_severity(key, value),
                "title": _find_title(key, value),
                "description": f"维度 {key} 风险分值为 {value} 分",
                "suggestion": f"建议重点排查 {_find_category_name(key)} 方面的问题",
                "metrics": {key: value},
            }
        )
    return findings


@router.get("/enterprises/{enterprise_id}/tax-preference")
async def get_tax_preference(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """税收优惠校验"""
    ent_id = str(enterprise_id)
    enterprise = await _get_enterprise(db, ent_id, tenant_id)
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    rev = float(enterprise.revenue_annual or 0)
    pref_result = check_tax_preference(
        PreferenceCheckInput(
            employee_count=enterprise.employee_count or 0,
            total_assets=rev,  # 近似
            annual_profit=int(rev * 0.1),  # 估算10%利润率
            is_high_tech=enterprise.is_high_tech,
            is_small_micro=enterprise.is_small_micro,
            industry=str(enterprise.industry),
        )
    )

    latest_risk = await _get_latest_risk_assessment(db, ent_id)
    compliance_adj = await _get_compliance_adjustment(
        db,
        ent_id,
        base_score=float(latest_risk.overall_risk_score or 0) if latest_risk else 0.0,
    )

    return success_response(
        TaxPreferenceResponse.model_validate(
            {
                "is_small_micro": enterprise.is_small_micro,
                "small_micro_eligible": pref_result.small_micro_eligible,
                "small_micro_conditions": pref_result.small_micro_conditions,
                "is_high_tech": enterprise.is_high_tech,
                "high_tech_risk": pref_result.high_tech_risk,
                "current_status": pref_result.current_status,
                "industry_preferences": pref_result.industry_preferences,
                "recommendations": pref_result.recommendations,
                "business_narrative": pref_result.business_narrative,
                "technical_summary": pref_result.technical_summary,
                "compliance_risk_level": (
                    compliance_adj["adjusted_level"] if compliance_adj else None
                ),
            }
        ).model_dump()
    )


@router.get("/enterprises/{enterprise_id}/intervention")
async def get_intervention(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取心理干预策略"""
    ent_id = str(enterprise_id)
    enterprise = await _get_enterprise(db, ent_id, tenant_id)
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 获取最新风险等级和偏差指数
    risk_level = "low"
    deviation_index = 30.0
    dominant_biases: list[str] = []

    latest_risk = await _get_latest_risk_assessment(db, ent_id)
    if latest_risk:
        risk_level = (
            latest_risk.overall_risk_level.value
            if latest_risk.overall_risk_level
            else "low"
        )

    latest_profile = await _get_latest_profile(db, ent_id)
    if latest_profile:
        deviation_index = float(latest_profile.deviation_index or 0)
        dominant_biases = _derive_dominant_biases(latest_profile, enterprise)

    # 合规调整 → 干预输入改用调整后等级/分数（与展示链路联动，避免"面板显示低风险、话术说高风险"）
    compliance_adj = await _get_compliance_adjustment(
        db,
        ent_id,
        base_score=(
            float(latest_risk.overall_risk_score or 0) if latest_risk else 0.0
        ),
        compliance_findings_count=(
            _count_findings(latest_risk.risk_details) if latest_risk else None
        ),
    )
    input_risk_level = (
        compliance_adj["adjusted_level"] if compliance_adj else risk_level
    )
    input_risk_score = (
        compliance_adj["adjusted_score"] if compliance_adj else None
    )

    # 估算预期损失和整改成本
    rev_annual = float(enterprise.revenue_annual or 1000000)
    expected_loss = rev_annual * 0.05
    remediation_cost = expected_loss * 0.3

    intervention = generate_intervention(
        InterventionInput(
            risk_level=input_risk_level,
            risk_score=input_risk_score,
            deviation_index=deviation_index,
            dominant_biases=dominant_biases,
            audit_probability=(
                0.3 if input_risk_level in ("high", "critical")
                else 0.15 if input_risk_level == "medium_high"
                else 0.1 if input_risk_level == "medium"
                else 0.05
            ),
            expected_loss=expected_loss,
            remediation_cost=remediation_cost,
        )
    )

    return success_response(
        InterventionResponse.model_validate(
            {
                "layers": [
                    {
                        "layer": layer.layer,
                        "name": layer.name,
                        "theory": layer.theory,
                        "visual_type": layer.visual_type,
                        "content": layer.content,
                    }
                    for layer in intervention.layers
                ],
                "business_narrative": intervention.business_narrative,
                "technical_summary": intervention.technical_summary,
                "priority_bias": (
                    BIAS_CN.get(dominant_biases[0], dominant_biases[0])
                    if dominant_biases
                    else "none"
                ),
                "priority_order": intervention.priority_order,
                "compliance_risk_level": (
                    compliance_adj["adjusted_level"] if compliance_adj else None
                ),
            }
        ).model_dump()
    )


@router.post("/enterprises/{enterprise_id}/nbt-intervention")
async def get_nbt_intervention(
    enterprise_id: UUID,
    risk_data: dict[str, Any] | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_auditor),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    获取 NBT 三层行为干预（Nudge-Budge-Trudge）。

    调用大语言模型（DeepSeek/Qwen），基于传入的风险数据与企业画像，
    生成三层结构化的行为干预内容。原型阶段若LLM不可用则返回Mock降级。
    """
    ent_id = str(enterprise_id)
    risk_data = risk_data or {}

    # 加载企业信息补充风险数据
    enterprise = await _get_enterprise(db, ent_id, tenant_id)
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 补充风险等级
    latest_risk = await _get_latest_risk_assessment(db, ent_id)

    # 合并风险数据 — 白名单 + 递归净化，限制客户端直接影响 LLM 的载荷结构
    filtered_risk = _sanitize_client_risk_data(risk_data)
    enriched_risk_data: dict[str, Any] = {
        "enterprise_name": enterprise.name,
        "industry": str(enterprise.industry),
        "is_high_tech": enterprise.is_high_tech,
        "is_small_micro": enterprise.is_small_micro,
        "revenue_annual": float(enterprise.revenue_annual or 0),
        "employee_count": enterprise.employee_count or 0,
        "cost_rate_industry": float(enterprise.cost_rate_claimed or 0),
        "tax_rate_industry": float(enterprise.tax_rate_claimed or 0),
        "risk_level": latest_risk.overall_risk_level.value if latest_risk else "low",
        "overall_risk_score": float(latest_risk.overall_risk_score) if latest_risk else 0.0,
        **filtered_risk,
    }

    # ── P1: NPT 动态配比 ──
    dynamic_mix_data = None
    try:
        base_score = float(latest_risk.overall_risk_score or 0) if latest_risk else 0.0
        findings_count = _count_findings(latest_risk.risk_details) if latest_risk else 0
        compliance = await _get_compliance_adjustment(
            db,
            ent_id,
            base_score=base_score,
            compliance_findings_count=findings_count if latest_risk else None,
        )
        if compliance:
            if findings_count == 0 and latest_risk:
                findings_count = max(0, int(base_score // 15))

            risk_level_val = (
                latest_risk.overall_risk_level.value
                if latest_risk and latest_risk.overall_risk_level
                else "low"
            )
            npt_mix_result = compute_npt_mix(
                findings_count=findings_count,
                reduction_pct=compliance["reduction_pct"],
                is_fully_compliant=compliance["is_fully_compliant"],
                risk_level=risk_level_val,
                override_risk_level=compliance["adjusted_level"],
            )
            dynamic_mix_data = npt_mix_result.model_dump()
            # 注入动态配比到 enrichment，让 LLM 按配比调整输出
            enriched_risk_data["npt_mix"] = dynamic_mix_data["npt_mix"]
            enriched_risk_data["npt_primary_strategy"] = dynamic_mix_data[
                "primary_strategy"
            ]
            enriched_risk_data["npt_quadrant"] = dynamic_mix_data["quadrant_name"]
    except Exception:
        LOGGER.warning(
            "NPT动态配比计算失败，使用默认配比 enterprise_id=%s",
            ent_id[:8],
            exc_info=True,
        )

    try:
        nbt_response = await llm_intervention_service.generate_nbt_intervention(
            enriched_risk_data
        )
    except Exception:
        LOGGER.exception("NBT干预生成失败 enterprise_id=%s", ent_id[:8])
        return error_response(40002, "NBT干预生成失败，请稍后重试")

    result = nbt_response.model_dump()
    if dynamic_mix_data:
        result["dynamic_mix"] = dynamic_mix_data
    return success_response(result)


# ═══════════════════════════════════════════════════════════════
# P3: Trudge 救赎工具箱
# ═══════════════════════════════════════════════════════════════


@router.get("/enterprises/{enterprise_id}/self-audit-report")
async def get_self_audit_report(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    一键生成自查报告（Markdown 格式）。

    基于 compliance_checker 的 findings 自动生成结构化的企业税务合规自查报告，
    包含：自查综述、分项结果、合规整改建议、免责声明。
    """
    ent_id = str(enterprise_id)
    enterprise = await _get_enterprise(db, ent_id, tenant_id)
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 获取最新风险评估
    latest_risk = await _get_latest_risk_assessment(db, ent_id)

    risk_score = float(latest_risk.overall_risk_score) if latest_risk else 0.0
    risk_level = latest_risk.overall_risk_level.value if latest_risk else "low"

    findings = _build_self_audit_findings(
        latest_risk.risk_details if latest_risk else None
    )

    compliance_info = await _get_compliance_adjustment(
        db,
        ent_id,
        base_score=risk_score,
        compliance_findings_count=len(findings) if latest_risk else None,
    )

    report = generate_self_audit_report(
        enterprise_name=enterprise.name,
        industry=str(enterprise.industry),
        findings=findings,
        annual_revenue=float(enterprise.revenue_annual or 0),
        compliance_info=compliance_info,
        risk_score=risk_score,
        risk_level=risk_level,
    )

    return success_response({
        "report_id": report.report_id,
        "enterprise_name": report.enterprise_name,
        "industry": report.industry,
        "generated_at": report.generated_at,
        "findings_summary": report.findings_summary,
        "findings_detail": report.findings_detail,
        "markdown_content": report.markdown_content,
        "risk_level": report.risk_level,
        "compliance_advice": report.compliance_advice,
    })


@router.get("/enterprises/{enterprise_id}/installment-simulation")
async def get_installment_simulation(
    enterprise_id: UUID,
    total_tax_due: float = 0,
    overdue_days: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    分期补税模拟。

    对比一次性补缴 vs 3/6/12期分期补缴的现金流影响。
    可按查询参数指定应补税款总额和逾期天数，不传则从风险数据自动推算。
    """
    ent_id = str(enterprise_id)
    enterprise = await _get_enterprise(db, ent_id, tenant_id)
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 自动推算应补税款（从风险评估的 compound_penalty_exposure）
    if total_tax_due <= 0:
        latest_risk = await _get_latest_risk_assessment(db, ent_id)
        if latest_risk:
            total_tax_due = float(latest_risk.compound_penalty_exposure or 0)
        if total_tax_due <= 0:
            # 从年营收估算（5% 为补税估算）
            total_tax_due = float(enterprise.revenue_annual or 1000000) * 0.05

    comparison = simulate_installment_payment(
        total_tax_due=total_tax_due,
        annual_revenue=float(enterprise.revenue_annual or 0),
        overdue_days=overdue_days,
    )

    return success_response(comparison.model_dump())


# ── 辅助函数（合规发现分类映射） ──

def _find_category(rule_key: str) -> str:
    return RISK_CATEGORY_MAPPING.get(rule_key, "other")


def _find_category_name(rule_key: str) -> str:
    return RISK_CATEGORY_NAME_MAPPING.get(rule_key, rule_key)


def _find_severity(rule_key: str, value: float) -> str:
    if value >= 75:
        return "high"
    if value >= 30:
        return "medium"
    return "low"


def _find_title(rule_key: str, value: float) -> str:
    sev = "严重" if value >= 75 else "中" if value >= 30 else "轻度"
    name = _find_category_name(rule_key)
    return f"{name}风险—风险评分 {value:.0f} 分（{sev}）"
