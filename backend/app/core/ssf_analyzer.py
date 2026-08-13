"""
SSF 博弈状态分析引擎

基于滑坡框架（Slippery Slope Framework, SSF）的二维诊断模型：
  X 轴 = 信任维度（对税务机关的尊重信任）
  Y 轴 = 权力维度（对税务机关执法能力的感知）

融合 NPT（Nudge-Budge-Trudge）行为干预模型，根据企业所处象限
动态推荐干预策略配比。

核心输出：
  - 权力坐标 (power_coord, 0-100)
  - 信任坐标 (trust_coord, 0-100)
  - 当前象限 (quadrant, I/II/III/IV)
  - 象限中文名称
  - NPT 策略配比 {nudge, budge, trudge}
  - 历史轨迹（可选）
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.psychological_profile import PsychologicalProfile
from app.models.risk_assessment import RiskAssessment
from app.core.compliance_adjustment import compute_compliance_adjusted_risk

_logger = logging.getLogger(__name__)

# ── 象限定义 ──
# 中心线：(50, 50)
CENTER = 50.0

QUADRANT_CONFIG = {
    "I": {
        "name": "合法合规",
        "subtitle": "权力与信任高度统一的最优均衡",
        "power_condition": "high",   # power >= 50
        "trust_condition": "high",   # trust >= 50
        "icon": "shield_check",      # 盾牌勾
        "color": "#10B981",          # 绿色
        "npt_mix": {"nudge": 0.90, "budge": 0.05, "trudge": 0.05},
        "primary_strategy": "nudge",
        "strategy_brief": "维持型助推：荣誉激励、信用积累、合规成就展示",
        "risk_trend": "stable_low",
    },
    "II": {
        "name": "博弈对抗",
        "subtitle": "高权力威慑下的表面服从，内心充满算计与侥幸",
        "power_condition": "high",
        "trust_condition": "low",
        "icon": "warning",
        "color": "#F59E0B",          # 琥珀色
        "npt_mix": {"nudge": 0.10, "budge": 0.70, "trudge": 0.20},
        "primary_strategy": "budge",
        "strategy_brief": "攻击性松动：损失可视化、同行震摄、权威具象化",
        "risk_trend": "volatile",
    },
    "III": {
        "name": "放弃合规",
        "subtitle": "既不信任也无所畏惧，已进入隐匿/虚开等高危行为",
        "power_condition": "low",
        "trust_condition": "low",
        "icon": "alert",
        "color": "#EF4444",          # 红色
        "npt_mix": {"nudge": 0.10, "budge": 0.20, "trudge": 0.70},
        "primary_strategy": "trudge",
        "strategy_brief": "救助型跋涉：结构化补救路径、分期补税、专家通道",
        "risk_trend": "critical",
    },
    "IV": {
        "name": "自愿遵从",
        "subtitle": "基于社会责任的自觉合规，但权力感知薄弱",
        "power_condition": "low",
        "trust_condition": "high",
        "icon": "heart",
        "color": "#3B82F6",          # 蓝色
        "npt_mix": {"nudge": 0.80, "budge": 0.10, "trudge": 0.10},
        "primary_strategy": "nudge",
        "strategy_brief": "强化型助推：温和展示权力维度、税收用途透明化",
        "risk_trend": "fragile",
    },
}

# ── 象限期望移动方向 ──
QUADRANT_TARGET = {
    "I": "维持当前位置，持续Nudge巩固",
    "II": "→ 目标移向第一象限：通过Budge打破侥幸心理，重建信任",
    "III": "→ 目标移向第二象限：先通过Trudge建立补救信任，再Budge施压",
    "IV": "→ 目标移向第一象限：通过Nudge强化权力感知，避免滑向第三象限",
}


@dataclass
class SSFState:
    """SSF 博弈状态"""
    enterprise_id: str
    enterprise_name: str

    # 坐标
    power_coord: float      # 权力感知 (0-100)
    trust_coord: float      # 信任程度 (0-100)

    # 象限
    quadrant: str            # "I" | "II" | "III" | "IV"
    quadrant_name: str       # 中文名称
    quadrant_subtitle: str
    quadrant_color: str
    quadrant_icon: str

    # NPT 策略
    npt_mix: dict            # {nudge, budge, trudge}
    primary_strategy: str    # "nudge" | "budge" | "trudge"
    strategy_brief: str
    target_direction: str    # 期望移动方向

    # 数据来源
    power_source: str        # 权力坐标计算依据
    trust_source: str        # 信任坐标计算依据
    adjusted_risk_score: float

    # 趋势
    risk_trend: str
    previous_quadrant: str | None = None
    movement_description: str = ""


@dataclass
class SSFHistoryPoint:
    """历史轨迹点"""
    date: str
    power_coord: float
    trust_coord: float
    quadrant: str
    event: str  # 触发事件描述


@dataclass
class SSFResult:
    """SSF 分析完整结果"""
    current_state: SSFState
    history: list[SSFHistoryPoint] = field(default_factory=list)
    all_enterprises_summary: list[dict] = field(default_factory=list)


def _compute_power_coord(risk_level: str, adjusted_score: float) -> float:
    """
    计算权力感知坐标。

    逻辑：风险等级越高 → 纳税人越感知到税务机关的执法威力 → 权力坐标越高。
    从 compliance_adjustment 的 adjusted_score 直接映射。
    """
    return min(100.0, max(0.0, adjusted_score))


def _compute_trust_coord(deviation_index: float | None) -> float:
    """
    计算信任坐标。

    逻辑：心理画像偏差指数越高 → 纳税人与合规标准的偏离越大 → 对税务机关的信任越低。
    trust = 100 - deviation_index
    """
    if deviation_index is None:
        return 50.0  # 无数据时默认中性
    return min(100.0, max(0.0, 100.0 - float(deviation_index)))


def _determine_quadrant(power: float, trust: float) -> str:
    """根据坐标判定象限"""
    if power >= CENTER and trust >= CENTER:
        return "I"
    elif power >= CENTER and trust < CENTER:
        return "II"
    elif power < CENTER and trust < CENTER:
        return "III"
    else:
        return "IV"


def _build_movement_description(current_q: str, previous_q: str | None) -> str:
    """生成象限移动描述"""
    if previous_q is None or previous_q == current_q:
        return "状态稳定，保持在当前象限"

    improvements = {
        ("III", "II"): "正在从放弃状态中恢复，权力感知增强",
        ("III", "I"): "实现重大合规突破，已进入最优状态",
        ("III", "IV"): "信任正在重建，但仍需强化权力监管感知",
        ("II", "I"): "侥幸心理已破除，信任关系建立，进入合规正轨",
        ("II", "IV"): "权力威慑减弱，但信任水平提升——注意防范回弹",
        ("IV", "I"): "权力感知增强，最优均衡日趋稳固",
    }

    deteriorations = {
        ("I", "II"): "⚠ 信任下降，合规关系出现裂痕",
        ("I", "IV"): "⚠ 权力威慑弱化，需警惕自愿遵从的脆弱性",
        ("I", "III"): "⚠⚠ 严重退化，合规体系面临崩溃风险",
        ("II", "III"): "⚠ 对抗失败，陷入放弃状态——需要Trudge救助",
        ("IV", "III"): "⚠ 信任崩塌，从脆弱遵从坠入放弃状态",
    }

    key = (previous_q, current_q)
    if key in improvements:
        return f"✅ {improvements[key]}"
    if key in deteriorations:
        return f"{deteriorations[key]}"
    return f"象限移动: {previous_q} → {current_q}"


async def analyze_ssf_state(
    db: AsyncSession,
    enterprise_id: str,
    enterprise_name: str = "",
) -> SSFResult:
    """
    执行 SSF 博弈状态分析。

    数据来源：
      - 权力维度：compliance_adjustment.adjusted_score
      - 信任维度：psychological_profile.deviation_index（取最新）

    Returns:
        SSFResult: 包含当前状态、历史轨迹和同行摘要
    """
    # ── 1. 获取合规调整数据（权力维度） ──
    # 先获取最新 risk assessment 的评分作为 base
    risk_result = await db.execute(
        select(RiskAssessment).where(
            RiskAssessment.enterprise_id == enterprise_id
        ).order_by(desc(RiskAssessment.assessment_date)).limit(1)
    )
    risk_assessment = risk_result.scalar_one_or_none()
    base_score = float(risk_assessment.overall_risk_score) if risk_assessment else 50.0

    compliance = await compute_compliance_adjusted_risk(
        db, enterprise_id, base_score=base_score
    )
    adjusted_score = float(compliance["adjusted_score"])
    power_coord = _compute_power_coord(compliance["adjusted_level"], adjusted_score)

    # ── 2. 获取最新心理画像（信任维度） ──
    profile_result = await db.execute(
        select(PsychologicalProfile).where(
            PsychologicalProfile.enterprise_id == enterprise_id
        ).order_by(desc(PsychologicalProfile.created_at)).limit(1)
    )
    profile = profile_result.scalar_one_or_none()

    if profile:
        # 同样应用合规调整到 deviation_index
        raw_deviation = float(profile.deviation_index)
        adjusted_deviation = round(raw_deviation * (1 - compliance["reduction_pct"] * 0.5), 2)
        trust_coord = _compute_trust_coord(adjusted_deviation)
        trust_source = f"心理画像偏差指数 {raw_deviation:.1f}（合规调整为 {adjusted_deviation:.1f}）"
    else:
        trust_coord = 50.0
        trust_source = "无心理画像数据，使用默认中性值"

    # ── 3. 象限判定 ──
    quadrant_key = _determine_quadrant(power_coord, trust_coord)
    qconfig = QUADRANT_CONFIG[quadrant_key]

    # ── 4. 历史轨迹（最近的5个画像记录） ──
    history: list[SSFHistoryPoint] = []
    history_result = await db.execute(
        select(PsychologicalProfile).where(
            PsychologicalProfile.enterprise_id == enterprise_id
        ).order_by(desc(PsychologicalProfile.created_at)).limit(5)
    )
    profiles = history_result.scalars().all()

    # 同时获取历史 risk assessments 用于 power 维度
    risk_result = await db.execute(
        select(RiskAssessment).where(
            RiskAssessment.enterprise_id == enterprise_id
        ).order_by(desc(RiskAssessment.assessment_date)).limit(5)
    )
    risk_assessments = risk_result.scalars().all()

    # 构建历史点（取两者中较新的）
    for i, p in enumerate(reversed(profiles)):
        h_deviation = float(p.deviation_index)
        h_trust = _compute_trust_coord(h_deviation)
        # 从 risk assessment 取 power
        h_power = 50.0
        if i < len(risk_assessments):
            ra = list(reversed(risk_assessments))[i]
            h_power = float(ra.overall_risk_score)

        h_quadrant = _determine_quadrant(h_power, h_trust)

        history.append(SSFHistoryPoint(
            date=p.created_at.strftime("%Y-%m-%d") if p.created_at else "",
            power_coord=round(h_power, 1),
            trust_coord=round(h_trust, 1),
            quadrant=h_quadrant,
            event=f"心理画像生成" if i == len(profiles) - 1 else "状态快照",
        ))

    # ── 5. 前一象限判定 ──
    previous_q = history[-2].quadrant if len(history) >= 2 else None
    movement_desc = _build_movement_description(quadrant_key, previous_q)

    # ── 6. 构建当前状态 ──
    current_state = SSFState(
        enterprise_id=enterprise_id,
        enterprise_name=enterprise_name,
        power_coord=round(power_coord, 1),
        trust_coord=round(trust_coord, 1),
        quadrant=quadrant_key,
        quadrant_name=qconfig["name"],
        quadrant_subtitle=qconfig["subtitle"],
        quadrant_color=qconfig["color"],
        quadrant_icon=qconfig["icon"],
        npt_mix=qconfig["npt_mix"],
        primary_strategy=qconfig["primary_strategy"],
        strategy_brief=qconfig["strategy_brief"],
        target_direction=QUADRANT_TARGET.get(quadrant_key, ""),
        power_source=f"合规调整风险评分 {adjusted_score:.1f}",
        trust_source=trust_source,
        adjusted_risk_score=adjusted_score,
        risk_trend=qconfig["risk_trend"],
        previous_quadrant=previous_q,
        movement_description=movement_desc,
    )

    _logger.info(
        "SSF分析 | %s | power=%.1f trust=%.1f | Q%s (%s) | strategy=%s",
        enterprise_name[:8], power_coord, trust_coord,
        quadrant_key, qconfig["name"], qconfig["primary_strategy"],
    )

    return SSFResult(
        current_state=current_state,
        history=history,
    )


async def analyze_all_enterprises_ssf(
    db: AsyncSession,
    enterprise_summaries: list[dict],
) -> list[dict]:
    """
    批量分析多个企业的 SSF 状态（用于散点图对比）。

    Args:
        db: 数据库会话
        enterprise_summaries: 企业摘要列表，每个含 id, name

    Returns:
        每个企业的 SSF 坐标摘要
    """
    results = []
    for ent in enterprise_summaries:
        try:
            result = await analyze_ssf_state(db, ent["id"], ent.get("name", ""))
            state = result.current_state
            results.append({
                "enterprise_id": state.enterprise_id,
                "enterprise_name": state.enterprise_name,
                "power_coord": state.power_coord,
                "trust_coord": state.trust_coord,
                "quadrant": state.quadrant,
                "quadrant_name": state.quadrant_name,
                "quadrant_color": state.quadrant_color,
                "primary_strategy": state.primary_strategy,
                "adjusted_risk_score": state.adjusted_risk_score,
                "movement_description": state.movement_description,
            })
        except Exception as e:
            _logger.error("SSF analysis failed for enterprise %s: %s", ent.get("id", "")[:8], e)
            results.append({
                "enterprise_id": ent.get("id", ""),
                "enterprise_name": ent.get("name", ""),
                "power_coord": 50.0,
                "trust_coord": 50.0,
                "quadrant": "I",
                "quadrant_name": "数据不足",
                "quadrant_color": "#9CA3AF",
                "primary_strategy": "unknown",
                "adjusted_risk_score": 50.0,
                "movement_description": "SSF分析失败",
            })

    return results
