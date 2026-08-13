"""
风险模拟 API

POST /api/v1/enterprises/{id}/simulate          运行风险模拟
GET  /api/v1/case-studies                       获取案例库
GET  /api/v1/case-studies?industry={industry}   按行业筛选案例
"""
import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, success_response, error_response, require_viewer, require_auditor, get_current_tenant_id
from app.models.enterprise import Enterprise
from app.models.risk_assessment import RiskAssessment
from app.core.simulation_engine import run_simulation, SimulationInput, _compute_dynamic_risk_level, run_enhanced_simulation
from app.core.compliance_adjustment import compute_compliance_adjusted_risk
from app.models.user import User
from app.schemas.simulation import (
    SimulationRequest, SimulationResponse, CaseStudiesResponse,
)

router = APIRouter(tags=["风险模拟"])

# 加载案例库（异步线程安全）
_cases_cache: list | None = None
_cases_lock = asyncio.Lock()
_logger = logging.getLogger(__name__)


def _load_cases() -> list:
    global _cases_cache
    if _cases_cache is None:
        cases_path = Path(__file__).parent.parent / "data" / "case_studies.json"
        try:
            with open(cases_path, "r", encoding="utf-8") as f:
                _cases_cache = json.load(f)
        except FileNotFoundError:
            _logger.warning("案例库文件不存在: %s，返回空列表", cases_path)
            _cases_cache = []
        except json.JSONDecodeError as e:
            _logger.error("案例库文件解析失败: %s (%s)，返回空列表", cases_path, e)
            _cases_cache = []
    return _cases_cache


async def _load_cases_async() -> list:
    """异步安全的案例库读取"""
    async with _cases_lock:
        return _load_cases()


@router.post("/enterprises/{enterprise_id}/simulate")
async def run_simulation_endpoint(
    enterprise_id: UUID,
    request: SimulationRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_auditor),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """运行风险模拟"""
    ent_id = str(enterprise_id)
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == ent_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 获取企业历史风险等级
    risk_level = "low"
    risk_result = await db.execute(
        select(RiskAssessment).where(
            RiskAssessment.enterprise_id == enterprise_id
        ).order_by(RiskAssessment.assessment_date.desc()).limit(1)
    )
    latest = risk_result.scalar_one_or_none()
    if latest:
        risk_level = latest.overall_risk_level.value

    # ── 动态风险等级：从场景参数推算，覆盖静态历史数据 ──
    scenario_risk = _compute_dynamic_risk_level(request.monthly_hidden_revenue)
    # 取两者中更严重的等级（历史风险+当前隐匿行为叠加）
    risk_order = ["low", "medium", "medium_high", "high", "critical"]
    historical_idx = risk_order.index(risk_level)
    scenario_idx = risk_order.index(scenario_risk)
    effective_risk = risk_order[max(historical_idx, scenario_idx)]

    # ── 合规调整：已完成整改任务降低有效风险等级 ──
    try:
        compliance = await compute_compliance_adjusted_risk(db, ent_id)
        if compliance["reduction_pct"] >= 0.45:
            # 大幅降低了合规风险 → 下调一个等级
            compliance_idx = max(0, risk_order.index(effective_risk) - 1)
            effective_risk = risk_order[compliance_idx]
            _logger.info("模拟器合规调整: effective_risk %s -> %s (reduction=%.0f%%)",
                         risk_order[max(historical_idx, scenario_idx)], effective_risk,
                         compliance["reduction_pct"] * 100)
    except Exception:
        pass

    # ── 企业基础信息（用于增强模块） ──
    ent_name = enterprise.name or ""
    ent_credit = enterprise.credit_code or ""
    try:
        revenue_annual = float(enterprise.revenue_annual) if enterprise.revenue_annual else 0.0
    except (TypeError, ValueError):
        revenue_annual = 0.0

    sim_input = SimulationInput(
        monthly_hidden_revenue=request.monthly_hidden_revenue,
        comprehensive_tax_rate=request.comprehensive_tax_rate,
        risk_level=effective_risk,
        remediation_cost=request.remediation_cost,
        industry=enterprise.industry.value if hasattr(enterprise.industry, 'value') else str(enterprise.industry),
    )

    # 增强版模拟（包含损失具象化 Budge 升级）
    enhanced = run_enhanced_simulation(
        sim_input,
        enterprise_name=ent_name,
        credit_code=ent_credit,
        revenue_annual=revenue_annual,
    )
    sim_result = enhanced["simulation"]

    return success_response(
        SimulationResponse.model_validate({
            "time_points": [
                {
                    "period": tp.period,
                    "months_elapsed": tp.months_elapsed,
                    "path_a_cost": tp.path_a_cost,
                    "path_b_cost": tp.path_b_cost,
                    "cost_difference": tp.cost_difference,
                    "audit_probability": tp.audit_probability,
                    "expected_penalty": tp.expected_penalty,
                    "expected_late_fee": tp.expected_late_fee,
                    "total_hidden_tax": tp.total_hidden_tax,
                }
                for tp in sim_result.time_points
            ],
            "recommendation": sim_result.recommendation,
            "loss_frame_message": sim_result.loss_frame_message,
            "technical_summary": sim_result.technical_summary,
            "case_references": sim_result.case_references or [],
            "effective_risk_level": effective_risk,
            # ── Budge 升级：损失具象化增强 ──
            "third_party_consequences": enhanced.get("third_party_consequences"),
            "peer_pressure": enhanced.get("peer_pressure"),
            "official_notice": enhanced.get("official_notice"),
        }).model_dump()
    )


@router.get("/case-studies")
async def list_case_studies(
    industry: str | None = Query(None, description="行业筛选"),
    risk_level: str | None = Query(None, description="风险等级筛选"),
    _user: User = Depends(require_viewer),
):
    """获取案例库，支持按行业/风险等级筛选"""
    cases = await _load_cases_async()

    if isinstance(cases, dict):
        # 如果是按企业类型组织的，展开
        all_cases = []
        for key in cases:
            if isinstance(cases[key], list):
                all_cases.extend(cases[key])
            elif isinstance(cases[key], dict):
                for sub in cases[key].values():
                    if isinstance(sub, list):
                        all_cases.extend(sub)
        cases = all_cases

    if not isinstance(cases, list):
        cases = []

    filtered = []
    for case in cases:
        if industry and case.get("industry") != industry:
            continue
        if risk_level and case.get("risk_level") != risk_level:
            continue
        filtered.append({
            "case_id": case.get("case_id", case.get("id", "")),
            "industry": case.get("industry", ""),
            "risk_level": case.get("risk_level", ""),
            "title": case.get("title", ""),
            "summary": case.get("summary", ""),
            "key_findings": case.get("key_findings", []),
            "outcome": case.get("outcome", ""),
        })

    return success_response(
        CaseStudiesResponse.model_validate({
            "cases": filtered,
            "total": len(filtered),
        }).model_dump()
    )
