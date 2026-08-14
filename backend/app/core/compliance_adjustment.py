"""
合规整改联动——跨模块统一的合规调整风险评分

核心原则：
  1. 完成合规整改任务 → 风险评分降低（幅度与完成任务数成比例）
  2. 合规校验无发现（完全合规）→ 所有风险评级强制为 LOW
  3. 撤销合规任务 → 风险评分恢复

所有需要展示风险等级/评分的模块（驾驶舱、风险地图、心理画像、
合规导航、整改追踪、报告中心）应通过本模块获取合规调整后的统一评分。
"""
import logging
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remediation_task import RemediationTask, TaskStatus
from app.models.risk_assessment import AssessRiskLevel
from app.models.enterprise import Enterprise
from app.core.credit_veto import resolve_tax_credit_veto

_logger = logging.getLogger(__name__)

# ── 风险评分阈值 ──
RISK_THRESHOLDS = [
    (80, AssessRiskLevel.CRITICAL),
    (60, AssessRiskLevel.HIGH),
    (45, AssessRiskLevel.MEDIUM),
    (30, AssessRiskLevel.MEDIUM),  # medium_high → mapped to medium for simplicity
    (0, AssessRiskLevel.LOW),
]


def score_to_level(score: float) -> AssessRiskLevel:
    """将评分映射到风险等级"""
    for threshold, level in RISK_THRESHOLDS:
        if score >= threshold:
            return level
    return AssessRiskLevel.LOW


def level_to_frontend(level: AssessRiskLevel) -> str:
    """映射到前端 RiskLevel 类型（五级）"""
    mapping = {
        AssessRiskLevel.CRITICAL: "critical",
        AssessRiskLevel.HIGH: "high",
        AssessRiskLevel.MEDIUM: "medium_high",
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
        base_score: 原始风险评分（如无，默认 100 意为待评估）
        compliance_findings_count: 合规校验发现数（如无，不参与完全合规判断）

    Returns:
        {
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

    # 0.5 修复加分参数（B1 配置化：每任务降幅 / 降幅上限）
    from app.core.risk_config import get_risk_config
    _config = await get_risk_config(db)
    pct_per_task = _config.get("reduction_pct_per_task", 0.15)
    pct_max = _config.get("reduction_pct_max", 0.80)

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
    adjusted_level_enum = score_to_level(adjusted_score) if not is_fully_compliant else AssessRiskLevel.LOW
    adjusted_level = level_to_frontend(adjusted_level_enum)

    _logger.info(
        "合规调整 | enterprise=%s | base=%.1f | completed=%d | reduction=%.0f%% | adjusted=%.1f (%s) | fully_compliant=%s | veto=%s",
        enterprise_id[:8], raw_score, completion_count,
        reduction_pct * 100, adjusted_score, adjusted_level, is_fully_compliant,
        bool(veto_reason),
    )

    return {
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
) -> dict[str, dict]:
    """批量计算多企业的合规调整风险（一次 IN 查询，消除列表接口的 N+1）。

    Returns:
        {enterprise_id: {"adjusted_score", "adjusted_level", "completion_count",
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

    # 0.5 修复加分参数（B1 配置化）
    from app.core.risk_config import get_risk_config
    _config = await get_risk_config(db)
    pct_per_task = _config.get("reduction_pct_per_task", 0.15)
    pct_max = _config.get("reduction_pct_max", 0.80)

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

        raw_score = 100.0
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
            else score_to_level(adjusted_score)
        )
        adjusted[eid] = {
            "adjusted_score": round(adjusted_score, 2),
            "adjusted_level": level_to_frontend(adjusted_level_enum),
            "completion_count": completion_count,
            "is_fully_compliant": is_fully_compliant,
            "reduction_pct": round(reduction_pct, 4),
            "veto_reason": veto_reason,
        }

    return adjusted
