"""
NPT 动态配比引擎

根据 compliance_adjustment 的 reduction_pct、findings_count 和企业风险等级，
自动判定当前所处的 NPT 象限，动态配比三级干预（Nudge-Budge-Trudge）的输出强度。

象限逻辑（与 SSF 同源，但基于合规数据而非权力/信任坐标）：
  Q1 (合法合规)  → 高合规完成度，低发现数 → Nudge 维持
  Q2 (博弈对抗)  → 中度合规，高风险波动   → Budge 攻击性松动
  Q3 (放弃合规)  → 低合规度，高风险       → Trudge 救助跋涉
  Q4 (自愿遵从)  → 中等合规，风险可控     → Nudge+Budge 均衡

核心函数：
  compute_npt_mix() → 返回 {nudge, budge, trudge} 配比 + 象限信息
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field

_logger = logging.getLogger(__name__)


# ── 三维配比方案 ──
MIX_SCHEMES: dict[str, dict[str, float]] = {
    "Q1_nudge_maintain": {
        "nudge": 0.90, "budge": 0.05, "trudge": 0.05,
    },
    "Q2_budge_attack": {
        "nudge": 0.10, "budge": 0.70, "trudge": 0.20,
    },
    "Q3_trudge_rescue": {
        "nudge": 0.10, "budge": 0.20, "trudge": 0.70,
    },
    "Q4_balanced": {
        "nudge": 0.50, "budge": 0.35, "trudge": 0.15,
    },
}

# ── 配比方案描述 ──
SCHEME_DESCRIPTIONS: dict[str, str] = {
    "Q1_nudge_maintain": (
        "合法合规象限：企业合规度极高，风险可控。建议以 Nudge 助推为主（90%），"
        "通过荣誉激励、合规成就展示维持当前良好状态。"
    ),
    "Q2_budge_attack": (
        "博弈对抗象限：企业存在中度合规问题但整改意愿不足。建议以 Budge 攻击性松动为主（70%），"
        "通过损失可视化、同行震摄、权威具象化打破侥幸心理。"
    ),
    "Q3_trudge_rescue": (
        "放弃合规象限：企业合规度严重不足，需强制性干预。建议以 Trudge 救助跋涉为主（70%），"
        "提供详细的 SOP 整改清单，进行保姆式陪跑合规。"
    ),
    "Q4_balanced": (
        "自愿遵从象限：企业有一定合规意识但行动滞后。建议 Nudge+Budge 均衡配比，"
        "既保持正向激励又施加合理的损失压力。"
    ),
}


class NPTMixResult(BaseModel):
    """NPT 动态配比结果"""
    npt_mix: dict[str, float] = Field(
        ..., description="NPT 三级干预配比 {nudge, budge, trudge}"
    )
    quadrant: str = Field(
        ..., description="当前象限标识 Q1/Q2/Q3/Q4"
    )
    quadrant_name: str = Field(
        ..., description="象限中文名称"
    )
    scheme_id: str = Field(
        ..., description="配比方案 ID"
    )
    scheme_description: str = Field(
        ..., description="配比方案说明"
    )
    primary_strategy: str = Field(
        ..., description="主导策略 nudge/budge/trudge"
    )
    intensity: str = Field(
        ..., description="干预强度 light/moderate/strong/critical"
    )


def _determine_primary_strategy(mix: dict[str, float]) -> str:
    """从配比中确定主导策略"""
    return max(mix, key=mix.get)


def _determine_intensity(mix: dict[str, float]) -> str:
    """根据主导策略的占比确定干预强度"""
    primary = max(mix, key=mix.get)
    value = mix[primary]
    if primary == "budge" and value >= 0.70:
        return "critical"
    if primary == "trudge" and value >= 0.70:
        return "critical"
    if value >= 0.70:
        return "strong"
    if value >= 0.50:
        return "moderate"
    return "light"


def compute_npt_mix(
    findings_count: int,
    reduction_pct: float,
    is_fully_compliant: bool = False,
    risk_level: str = "low",
    override_risk_level: str | None = None,
) -> NPTMixResult:
    """
    根据合规调整数据计算 NPT 动态配比。

    Args:
        findings_count: 合规校验发现的问题数量
        reduction_pct: 已完成任务带来的风险降低百分比 (0-1)
        is_fully_compliant: 是否完全合规（0 findings）
        risk_level: 企业当前风险等级 (low/medium/medium_high/high/critical)
        override_risk_level: 可选的风险等级覆盖（e.g. 合规调整后等级）

    Returns:
        NPTMixResult: 包含配比、象限、策略说明的完整结果

    判定逻辑：

    ┌──────────────────────┬──────────────┬──────────┐
    │       条件            │   象限        │  主导策略 │
    ├──────────────────────┼──────────────┼──────────┤
    │ findings == 0         │   Q1 合法合规 │  Nudge   │
    │ 且 fully_compliant    │              │          │
    ├──────────────────────┼──────────────┼──────────┤
    │ findings < 5          │   Q4 自愿遵从 │  Nudge   │
    │ reduction >= 0.45     │              │  +Budge  │
    ├──────────────────────┼──────────────┼──────────┤
    │ findings >= 5         │   Q2 博弈对抗 │  Budge   │
    │ reduction < 0.2       │              │          │
    │ risk >= medium_high   │              │          │
    ├──────────────────────┼──────────────┼──────────┤
    │ findings >= 8         │   Q3 放弃合规 │  Trudge  │
    │ reduction < 0.15      │              │          │
    │ risk >= high          │              │          │
    ├──────────────────────┼──────────────┼──────────┤
    │ 其他/默认              │   Q4 自愿遵从 │  均衡    │
    └──────────────────────┴──────────────┴──────────┘
    """
    effective_risk = override_risk_level or risk_level

    # ── 判定象限 ──

    # Q1: 完全合规 → Nudge 维持
    if findings_count == 0 and (is_fully_compliant or reduction_pct >= 0.80):
        scheme_id = "Q1_nudge_maintain"
        quadrant = "Q1"
        quadrant_name = "合法合规"

    # Q3: 严重不合规 → Trudge 跋涉
    elif findings_count >= 8 and reduction_pct < 0.15 and effective_risk in ("high", "critical"):
        scheme_id = "Q3_trudge_rescue"
        quadrant = "Q3"
        quadrant_name = "放弃合规"

    # Q2: 中度问题 + 低整改 → Budge 攻击
    elif findings_count >= 5 and reduction_pct < 0.20 and effective_risk in ("medium_high", "high", "critical"):
        scheme_id = "Q2_budge_attack"
        quadrant = "Q2"
        quadrant_name = "博弈对抗"

    # Q4: 中等合规 → 均衡配比
    elif findings_count < 5 and reduction_pct >= 0.45:
        scheme_id = "Q4_balanced"
        quadrant = "Q4"
        quadrant_name = "自愿遵从"

    # 默认：根据 findings 数量做 fallback
    else:
        if findings_count >= 5:
            scheme_id = "Q2_budge_attack"
            quadrant = "Q2"
            quadrant_name = "博弈对抗"
        else:
            scheme_id = "Q4_balanced"
            quadrant = "Q4"
            quadrant_name = "自愿遵从"

    mix = MIX_SCHEMES[scheme_id]
    primary = _determine_primary_strategy(mix)
    intensity = _determine_intensity(mix)

    _logger.info(
        "NPT动态配比 | findings=%d | reduction=%.0f%% | compliant=%s | "
        "risk=%s | quadrant=%s(%s) | scheme=%s | primary=%s | intensity=%s",
        findings_count, reduction_pct * 100, is_fully_compliant,
        effective_risk, quadrant, quadrant_name, scheme_id, primary, intensity,
    )

    return NPTMixResult(
        npt_mix=mix,
        quadrant=quadrant,
        quadrant_name=quadrant_name,
        scheme_id=scheme_id,
        scheme_description=SCHEME_DESCRIPTIONS[scheme_id],
        primary_strategy=primary,
        intensity=intensity,
    )
