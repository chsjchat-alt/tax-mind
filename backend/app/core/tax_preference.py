"""
税收优惠适用性校验模块

功能：
  1. 小微企业优惠条件自动核验
  2. 高新技术企业资格动态监测
  3. 区域/行业专项优惠匹配

小微企业优惠条件（现行政策）：
  - 从业人数 ≤ 300人
  - 资产总额 ≤ 5000万元
  - 年度应纳税所得额 ≤ 300万元

高新技术企业动态监测：
  - 提示"动态摘帽"制度性常态
  - 提醒关注研发费用占比、高新收入占比等核心指标

商业语言输出：优惠适用性说明
技术语言输出：结构化校验结果
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# ── 小微企业门槛 ──
SMALL_MICRO_THRESHOLDS = {
    "max_employees": 300,
    "max_assets": Decimal("50000000"),          # 5000万元
    "max_annual_profit": Decimal("3000000"),    # 300万元
}

# ── 高企动态监测提示 ──
HIGH_TECH_MONITORING_NOTE = (
    "【高企动态监测提醒】2025年全国取消高新技术企业资格4758家，"
    "同比增长11.77%。高企'动态摘帽'已成为制度性常态，"
    "请持续关注以下核心指标：\n"
    "  1. 研发费用占销售收入比例 ≥ 3%（最近一年销售收入 < 5000万元）\n"
    "  2. 高新技术产品（服务）收入占企业同期总收入 ≥ 60%\n"
    "  3. 科技人员占企业当年职工总数 ≥ 10%\n"
    "  4. 企业创新能力评价达到相应要求\n"
    "  5. 申请认定前一年内未发生重大安全、质量事故或严重环境违法行为"
)

# ── 行业专项优惠参考 ──
INDUSTRY_PREFERENCES = {
    "制造": ["研发费用加计扣除", "固定资产加速折旧", "先进制造业增值税加计抵减"],
    "批发零售": ["小型微利企业所得税优惠"],
    "建筑": ["简易计税方法选择权（清包工/甲供材）"],
    "电商": ["跨境电商零售出口免税", "小型微利企业所得税优惠"],
    "餐饮服务": ["生活性服务业增值税加计抵减", "小型微利企业所得税优惠"],
}


class PreferenceCheckInput(BaseModel):
    """优惠校验输入"""
    employee_count: int = Field(..., ge=0, description="从业人数")
    total_assets: Decimal = Field(..., ge=0, description="资产总额（元）")
    annual_profit: Decimal = Field(..., description="年度应纳税所得额（元）")
    is_high_tech: bool = Field(default=False, description="是否高新技术企业")
    is_small_micro: bool = Field(default=False, description="是否当前享受小微优惠")
    industry: str = Field(default="制造", description="所属行业")


class PreferenceCheckResult(BaseModel):
    """优惠校验结果"""
    small_micro_eligible: bool = False                          # 是否符合小微条件
    small_micro_conditions: dict = Field(default_factory=dict)  # 各条件明细
    current_status: Literal[
        "enjoying_correctly",
        "enjoying_incorrectly",
        "should_enjoy_but_not",
        "not_applicable",
    ] = "not_applicable"
    recommendations: list[str] = Field(default_factory=list)   # 建议
    high_tech_risk: str | None = None                           # 高企动态监测风险提示
    industry_preferences: list[str] = Field(default_factory=list)  # 行业专项优惠
    business_narrative: str = ""                                # 商业语言叙述
    technical_summary: dict = Field(default_factory=dict)       # 技术语言摘要


def _check_small_micro_conditions(data: PreferenceCheckInput) -> dict:
    """逐项检查小微企业条件"""
    return {
        "employee_count": {
            "value": data.employee_count,
            "threshold": SMALL_MICRO_THRESHOLDS["max_employees"],
            "passed": data.employee_count <= SMALL_MICRO_THRESHOLDS["max_employees"],
        },
        "total_assets": {
            "value": data.total_assets,
            "threshold": SMALL_MICRO_THRESHOLDS["max_assets"],
            "passed": data.total_assets <= SMALL_MICRO_THRESHOLDS["max_assets"],
        },
        "annual_profit": {
            "value": data.annual_profit,
            "threshold": SMALL_MICRO_THRESHOLDS["max_annual_profit"],
            "passed": data.annual_profit <= SMALL_MICRO_THRESHOLDS["max_annual_profit"],
        },
    }


def _determine_status(
    eligible: bool,
    is_small_micro: bool,
    recommendations: list[str],
) -> str:
    """根据资格和当前状态判断优惠享受情况"""
    if eligible and is_small_micro:
        return "enjoying_correctly"
    elif eligible and not is_small_micro:
        recommendations.insert(0, "贵企业符合小微企业条件但尚未享受优惠，建议向税务机关申请认定。")
        return "should_enjoy_but_not"
    elif not eligible and is_small_micro:
        recommendations.insert(0, "贵企业当前享受小微企业优惠但已不满足条件，请尽快自查并主动调整，避免后续被追缴。")
        return "enjoying_incorrectly"
    else:
        return "not_applicable"


def _generate_business_narrative(result: PreferenceCheckResult, data: PreferenceCheckInput) -> str:
    """生成商业语言叙述"""
    parts = []

    # 小微结果
    if result.small_micro_eligible:
        parts.append("✅ 贵企业符合小型微利企业认定条件，可享受企业所得税优惠税率。")
        conds = result.small_micro_conditions
        parts.append(f"  · 从业人数 {conds['employee_count']['value']} 人 ≤ {SMALL_MICRO_THRESHOLDS['max_employees']} 人 ✓")
        parts.append(f"  · 资产总额 {float(conds['total_assets']['value'])/10000:.0f} 万元 ≤ {float(SMALL_MICRO_THRESHOLDS['max_assets'])/10000:.0f} 万元 ✓")
        parts.append(f"  · 应纳税所得额 {float(conds['annual_profit']['value'])/10000:.0f} 万元 ≤ {float(SMALL_MICRO_THRESHOLDS['max_annual_profit'])/10000:.0f} 万元 ✓")
    else:
        parts.append("❌ 贵企业不完全符合小型微利企业条件。")
        conds = result.small_micro_conditions
        for key, label in [("employee_count", "从业人数"), ("total_assets", "资产总额"), ("annual_profit", "应纳税所得额")]:
            c = conds[key]
            if not c["passed"]:
                parts.append(f"  · {label}不满足：{c['value']} > {c['threshold']} ✗")

    parts.append("")

    # 当前状态
    status_map = {
        "enjoying_correctly": "当前正确享受小微企业优惠，状态正常。",
        "enjoying_incorrectly": "⚠️ 当前享受小微企业优惠但已不满足条件，存在被追缴风险。",
        "should_enjoy_but_not": "贵企业符合条件但未享受优惠，建议尽快申请。",
        "not_applicable": "贵企业不适用小微企业优惠。",
    }
    parts.append(status_map.get(result.current_status, ""))

    # 高企提示
    if data.is_high_tech:
        parts.append("")
        parts.append("【高新技术企业资格动态监测提示】")
        parts.append(HIGH_TECH_MONITORING_NOTE)

    # 行业优惠
    if result.industry_preferences:
        parts.append("")
        parts.append(f"可关注的{data.industry}行业专项优惠：")
        for pref in result.industry_preferences:
            parts.append(f"  · {pref}")

    # 建议
    if result.recommendations:
        parts.append("")
        parts.append("行动建议：")
        for i, rec in enumerate(result.recommendations, 1):
            parts.append(f"  {i}. {rec}")

    return "\n".join(parts)


def check_tax_preference(data: PreferenceCheckInput) -> PreferenceCheckResult:
    """
    校验企业税收优惠适用性。

    Args:
        data: 优惠校验输入数据

    Returns:
        PreferenceCheckResult: 校验结果和建议

    Edge Cases:
      - 各项指标恰好等于阈值：视为满足条件
      - 零值输入：仍可正常判断
      - 未知行业：不返回行业专项优惠
    """
    result = PreferenceCheckResult()

    # ── 小微企业条件核验 ──
    conditions = _check_small_micro_conditions(data)
    result.small_micro_conditions = conditions

    result.small_micro_eligible = (
        conditions["employee_count"]["passed"]
        and conditions["total_assets"]["passed"]
        and conditions["annual_profit"]["passed"]
    )

    # ── 当前状态判断 ──
    result.current_status = _determine_status(
        result.small_micro_eligible, data.is_small_micro, result.recommendations
    )

    # ── 高企动态监测 ──
    if data.is_high_tech:
        result.high_tech_risk = HIGH_TECH_MONITORING_NOTE
        result.recommendations.append(
            "作为高新技术企业，请每季度自查研发费用占比和高新收入占比，防止'动态摘帽'。"
        )

    # ── 行业专项优惠 ──
    result.industry_preferences = INDUSTRY_PREFERENCES.get(data.industry, [])

    if result.industry_preferences:
        result.recommendations.append(
            f"可关注{data.industry}行业专项优惠，详见上述列表。"
        )

    # ── 商业语言 ──
    result.business_narrative = _generate_business_narrative(result, data)

    # ── 技术摘要 ──
    result.technical_summary = {
        "small_micro_eligible": result.small_micro_eligible,
        "conditions": {
            k: {"value": v["value"], "threshold": v["threshold"], "passed": v["passed"]}
            for k, v in conditions.items()
        },
        "current_status": result.current_status,
        "is_high_tech": data.is_high_tech,
        "high_tech_monitoring": data.is_high_tech,
        "industry": data.industry,
        "industry_preferences": result.industry_preferences,
        "recommendations_count": len(result.recommendations),
    }

    return result
