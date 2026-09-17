"""
合规整改联动——跨模块统一的合规调整风险评分

核心原则：
  1. 完成合规整改任务 → 风险评分降低（幅度与完成任务数成比例）
  2. 合规校验无发现（完全合规）→ 所有风险评级强制为 LOW
  3. 撤销合规任务 → 风险评分恢复

所有需要展示风险等级/评分的模块（驾驶舱、风险地图、
合规导航、整改追踪、报告中心）应通过本模块获取合规调整后的统一评分。
"""
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remediation_task import RemediationTask, TaskStatus
from app.models.risk_assessment import RiskAssessment, AssessRiskLevel
from app.models.enterprise import Enterprise
from app.core.credit_veto import resolve_tax_credit_veto

_logger = logging.getLogger(__name__)


def _count_findings(risk_details: Any) -> int:
    """统计风险明细中的正向发现数（正数数值键计为 1 个发现）。"""
    if not isinstance(risk_details, dict):
        return 0
    return sum(
        1 for v in risk_details.values() if isinstance(v, (int, float)) and v > 0
    )


# ── 风险评分阈值（默认值；与 risk_config 键一一对应，可配置化）──
DEFAULT_THRESHOLDS: dict[str, float] = {
    "critical": 80.0,
    "high": 60.0,
    "medium_high": 45.0,
    "medium": 30.0,
}


def _load_thresholds(config: dict[str, Any]) -> dict[str, float]:
    """从 risk_config 读取五级阈值（缺键回退代码内默认值）。"""
    return {
        "critical": float(
            config.get("risk_critical_threshold", DEFAULT_THRESHOLDS["critical"])
        ),
        "high": float(
            config.get("risk_high_level_threshold", DEFAULT_THRESHOLDS["high"])
        ),
        "medium_high": float(
            config.get("risk_medium_high_threshold", DEFAULT_THRESHOLDS["medium_high"])
        ),
        "medium": float(
            config.get("risk_medium_level_threshold", DEFAULT_THRESHOLDS["medium"])
        ),
    }


def score_to_level(
    score: float,
    thresholds: dict[str, float] | None = None,
) -> AssessRiskLevel:
    """将评分映射到风险等级（内部四档枚举；中档由 level_to_frontend 细分为 medium/medium_high）"""
    th = thresholds or DEFAULT_THRESHOLDS
    if score >= th["critical"]:
        return AssessRiskLevel.CRITICAL
    if score >= th["high"]:
        return AssessRiskLevel.HIGH
    if score >= th["medium"]:
        return AssessRiskLevel.MEDIUM
    return AssessRiskLevel.LOW


def level_to_frontend(
    level: AssessRiskLevel,
    score: float | None = None,
    thresholds: dict[str, float] | None = None,
) -> str:
    """映射到前端 RiskLevel 类型（五级）"""
    th = thresholds or DEFAULT_THRESHOLDS
    if level == AssessRiskLevel.MEDIUM:
        # 分 < medium_high 阈值为中风险(medium)，否则为中高风险(medium_high)
        if score is None or score >= th["medium_high"]:
            return "medium_high"
        return "medium"
    mapping = {
        AssessRiskLevel.CRITICAL: "critical",
        AssessRiskLevel.HIGH: "high",
        AssessRiskLevel.LOW: "low",
    }
    return mapping.get(level, "medium")


async def compute_compliance_adjusted_risk(
    db: AsyncSession,
    enterprise_id: str,
    base_score: float | None = None,
    compliance_findings_count: int | None = None,
) -> dict:
    """计算合规调整后的统一风险评分和等级。

    Args:
        db: 数据库会话
        enterprise_id: 企业 ID
        base_score: 原始风险评分（如无，自动兜底取该企业最新一次风险评估分）
        compliance_findings_count: 合规校验发现数（如无，自动兜底取最新评估的发现数）

    Returns:
        {
            "original_score": float,      # 原始风险评分 (0-100)
            "original_level": str,        # 原始风险等级 (frontend RiskLevel)
            "adjusted_score": float,      # 调整后评分 (0-100)
            "adjusted_level": str,        # 调整后等级 (frontend RiskLevel)
            "completion_count": int,      # 已完成合规任务数
            "is_fully_compliant": bool,   # 是否完全合规
            "reduction_pct": float,        # 风险降低百分比
            "veto_reason": str | None,    # 一票否决原因（触发时返回，修复加分不计）
        }
    """
    # 0. 一票否决判定（纳税信用 D 级 / 涉税犯罪 → R 不计，评分不因整改下调）
    ent_result = await db.execute(
        select(Enterprise).where(Enterprise.id == enterprise_id)
    )
    enterprise = ent_result.scalar_one_or_none()
    veto_reason = (
        resolve_tax_credit_veto(
            enterprise.tax_credit_level,
            enterprise.tax_crime_convicted,
        )
        if enterprise is not None else None
    )

    # 0.5 修复加分参数（B1 配置化：每任务降幅 / 降幅上限 / 五级阈值）
    from app.core.risk_config import get_risk_config
    _config = await get_risk_config(db)
    pct_per_task = _config.get("reduction_pct_per_task", 0.15)
    pct_max = _config.get("reduction_pct_max", 0.80)
    thresholds = _load_thresholds(_config)

    # 0.6 兜底取数：未传 base_score / findings 时自动查最新评估，保证
    #     所有调用点（risk_scan/upload/simulation/compliance_check/reports/remediation 等）
    #     统一走同一口径，避免各接口因漏传参数而偏离真实风险分。
    if base_score is None or compliance_findings_count is None:
        ra_result = await db.execute(
            select(RiskAssessment)
            .where(RiskAssessment.enterprise_id == enterprise_id)
            .order_by(RiskAssessment.assessment_date.desc())
            .limit(1)
        )
        latest_ra = ra_result.scalar_one_or_none()
        if base_score is None and latest_ra is not None and latest_ra.overall_risk_score is not None:
            base_score = float(latest_ra.overall_risk_score)
        if compliance_findings_count is None and latest_ra is not None:
            compliance_findings_count = _count_findings(latest_ra.risk_details)

    # 1. 查询已完成的合规整改任务
    completed_result = await db.execute(
        select(RemediationTask).where(
            RemediationTask.enterprise_id == enterprise_id,
            RemediationTask.status == TaskStatus.COMPLETED,
            RemediationTask.source == "compliance",
        )
    )
    completed_tasks = completed_result.scalars().all()
    completion_count = len(completed_tasks)

    # 2. 完全合规判断：无合规发现 = 完全合规
    is_fully_compliant = (
        compliance_findings_count is not None
        and compliance_findings_count == 0
    )

    # 3. 计算风险降低幅度
    # 每个完成的合规任务降低 pct_per_task 风险（最多降低 pct_max）
    if completion_count == 0:
        reduction_pct = 0.0
    else:
        reduction_pct = min(pct_max, completion_count * pct_per_task)

    # 4. 计算调整后评分
    raw_score = base_score if base_score is not None else 100.0
    if veto_reason:
        # 一票否决触发 → 修复加分 R 不计，评分保持原始风险分不变
        adjusted_score = raw_score
        is_fully_compliant = False
    elif is_fully_compliant:
        # 完全合规 → 强制低风险
        adjusted_score = 10.0
    else:
        adjusted_score = raw_score * (1.0 - reduction_pct)

    # 5. 确定风险等级
    adjusted_level_enum = (
        score_to_level(adjusted_score, thresholds)
        if not is_fully_compliant
        else AssessRiskLevel.LOW
    )
    adjusted_level = level_to_frontend(adjusted_level_enum, adjusted_score, thresholds)
    original_level = level_to_frontend(
        score_to_level(raw_score, thresholds), raw_score, thresholds
    )

    _logger.info(
        "合规调整 | enterprise=%s | base=%.1f | completed=%d | reduction=%.0f%% | adjusted=%.1f (%s) | fully_compliant=%s | veto=%s",
        enterprise_id[:8], raw_score, completion_count,
        reduction_pct * 100, adjusted_score, adjusted_level, is_fully_compliant,
        bool(veto_reason),
    )

    return {
        "original_score": round(raw_score, 2),
        "original_level": original_level,
        "adjusted_score": round(adjusted_score, 2),
        "adjusted_level": adjusted_level,
        "completion_count": completion_count,
        "is_fully_compliant": is_fully_compliant,
        "reduction_pct": round(reduction_pct, 4),
        "veto_reason": veto_reason,
    }


async def compute_compliance_adjusted_risks(
    db: AsyncSession,
    enterprise_ids: list[str],
    compliance_findings_counts: dict[str, int] | None = None,
    base_scores: dict[str, float] | None = None,
) -> dict[str, dict]:
    """批量计算多企业的合规调整风险（一次 IN 查询，消除列表接口的 N+1）。

    Args:
        base_scores: 各企业原始风险评分 {enterprise_id: score}；缺失企业回退 100。

    Returns:
        {enterprise_id: {"original_score", "original_level", "adjusted_score",
                         "adjusted_level", "completion_count",
                         "is_fully_compliant", "reduction_pct"}}
    """
    if not enterprise_ids:
        return {}

    # 0. 批量加载一票否决标志（纳税信用 D 级 / 涉税犯罪 → R 不计）
    veto_map: dict[str, str | None] = {}
    ent_result = await db.execute(
        select(Enterprise).where(Enterprise.id.in_(enterprise_ids))
    )
    for ent in ent_result.scalars().all():
        veto_map[ent.id] = resolve_tax_credit_veto(
            ent.tax_credit_level, ent.tax_crime_convicted,
        )

    # 0.5 修复加分参数（B1 配置化：每任务降幅 / 降幅上限 / 五级阈值）
    from app.core.risk_config import get_risk_config
    _config = await get_risk_config(db)
    pct_per_task = _config.get("reduction_pct_per_task", 0.15)
    pct_max = _config.get("reduction_pct_max", 0.80)
    thresholds = _load_thresholds(_config)

    # 一次聚合查询所有企业的已完成合规任务数
    result = await db.execute(
        select(
            RemediationTask.enterprise_id,
            func.count().label("completed_count"),
        ).where(
            RemediationTask.enterprise_id.in_(enterprise_ids),
            RemediationTask.status == TaskStatus.COMPLETED,
            RemediationTask.source == "compliance",
        ).group_by(RemediationTask.enterprise_id)
    )
    counts = {eid: cnt for eid, cnt in result.all()}

    adjusted: dict[str, dict] = {}
    for eid in enterprise_ids:
        completion_count = counts.get(eid, 0)
        veto_reason = veto_map.get(eid)
        is_fully_compliant = bool(
            compliance_findings_counts
            and compliance_findings_counts.get(eid) == 0
        )

        if completion_count == 0:
            reduction_pct = 0.0
        else:
            reduction_pct = min(pct_max, completion_count * pct_per_task)

        raw_score = (base_scores or {}).get(eid, 100.0)
        if veto_reason:
            # 一票否决触发 → 修复加分 R 不计，评分保持原始风险分不变
            adjusted_score = raw_score
            is_fully_compliant = False
        elif is_fully_compliant:
            adjusted_score = 10.0
        else:
            adjusted_score = raw_score * (1.0 - reduction_pct)

        adjusted_level_enum = (
            AssessRiskLevel.LOW
            if is_fully_compliant
            else score_to_level(adjusted_score, thresholds)
        )
        adjusted[eid] = {
            "original_score": round(raw_score, 2),
            "original_level": level_to_frontend(
                score_to_level(raw_score, thresholds), raw_score, thresholds
            ),
            "adjusted_score": round(adjusted_score, 2),
            "adjusted_level": level_to_frontend(
                adjusted_level_enum, adjusted_score, thresholds
            ),
            "completion_count": completion_count,
            "is_fully_compliant": is_fully_compliant,
            "reduction_pct": round(reduction_pct, 4),
            "veto_reason": veto_reason,
        }

    return adjusted
