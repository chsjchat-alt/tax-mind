"""
心理画像评分模型

将行为经济学/认知心理学引入财税合规领域：
基于企业的财税行为数据（私卡比例、税负偏离度、历史风险记录、整改完成率等），
推断老板的六类认知偏差程度，输出 0-100 标准化偏差得分和干预策略。

六维认知偏差模型：
  1. 掌控欲       —— 私卡使用、对公账户混用
  2. 损失厌恶     —— 税负率远低于行业均值（极度避税）
  3. 乐观偏差     —— 高风险行为持续不改（觉得不会被查）
  4. 控制错觉     —— 四流严重不匹配却照常经营
  5. 短期主义     —— 隐匿收入、追求短期现金流
  6. 防御心理     —— 整改任务完成率低、抗拒合规改变

商业语言输出：面向老板的认知偏差解读和心理干预建议
技术语言输出：标准化偏差得分和维度详情
"""

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path
from typing import Any

import json

# ── 加载分行业×规模的六维偏差基准数据 ──
_BENCHMARKS_PATH = Path(__file__).resolve().parent.parent / "data" / "profile_benchmarks.json"
with open(_BENCHMARKS_PATH, "r", encoding="utf-8") as _f:
    _PROFILE_BENCHMARKS = json.load(_f)

# ── 偏差类型定义 ──
BIAS_CN = {
    "control_desire": "掌控欲",
    "loss_aversion": "损失厌恶",
    "optimism_bias": "乐观偏差",
    "control_illusion": "控制错觉",
    "short_termism": "短期主义",
    "defensiveness": "防御心理",
}

# ── 干预策略模板 ──
INTERVENTION_STRATEGIES = {
    "control_desire": {
        "high": "您习惯亲力亲为掌控资金流向，但私卡收款反而会引来更大关注。建议将经营资金统一纳入对公账户，合规经营才是真正的掌控。",
        "medium": "对资金流向的掌控感可以理解，但部分私卡操作存在隐患。逐步将核心业务对公化，让每一笔钱都有据可查。",
        "low": "资金管理规范，继续保持。",
    },
    "loss_aversion": {
        "high": "极度厌恶税务成本可能导致更大的损失——金税四期下被稽查的罚款远高于正常纳税。请考虑，合规纳税是最经济的长期策略。",
        "medium": "对税负的敏感可以理解，但过低税负率已成为稽查重点指标。适当提高申报质量，用合规换取安心。",
        "low": "税负管理合理，在合规与成本之间取得了良好平衡。",
    },
    "optimism_bias": {
        "high": "您可能低估了金税四期的稽查能力。大数据比对能在几分钟内发现异常，与其赌不被查到，不如主动合规。",
        "medium": "过去未被稽查不代表未来安全。金税四期的数据比对能力逐年增强，建议减少侥幸心理。",
        "low": "对税务风险有清醒认识，保持警觉是好事。",
    },
    "control_illusion": {
        "high": "四流严重不匹配意味着您的业务链条存在较大漏洞。即使目前未被稽查，这些数据痕迹在金税四期系统中清晰可见。",
        "medium": "部分业务流程的匹配度存在不足。这不是可控的风险，而是已被系统标记的疑点，建议尽快梳理。",
        "low": "业务流程规范，四流匹配度良好，继续保持。",
    },
    "short_termism": {
        "high": "隐匿收入换取短期现金流，牺牲的是企业长期发展空间。合规企业更容易获得银行贷款、政府补贴和商业合作机会。",
        "medium": "短期现金流压力可以理解，但长期来看，合规经营才能让企业走得更远。建议制定分阶段的合规计划。",
        "low": "注重企业长期发展，合规意识较强。",
    },
    "defensiveness": {
        "high": "对整改建议的抵触心态可能源于对变化的不确定感。请理解，每次整改都是降低您个人连带责任风险的机会。",
        "medium": "部分整改任务推进缓慢。建议从最简单的一项开始，逐步建立合规信心。",
        "low": "对整改持开放态度，积极配合合规改进。",
    },
}


@dataclass
class BehavioralData:
    """企业行为数据输入"""
    private_card_ratio: float                        # 私卡收款占比 0-1
    tax_burden_deviation: float                      # 税负率偏离行业均值（百分点，正=低于行业）
    historical_risk_count: int                       # 历史风险记录数
    risk_recurrence_rate: float                      # 风险复发率 0-1
    four_flow_match_score: float                     # 四流匹配度 0-100
    undeclared_revenue_ratio: float                  # 未申报收入占比 0-1
    remediation_completion_rate: float               # 整改任务完成率 0-100
    consecutive_high_risk_periods: int               # 连续高风险期数
    is_high_tech: bool = False                       # 是否高新技术企业
    is_small_micro: bool = True                      # 是否小微企业
    revenue_annual: float = 0.0                      # 年营收（元）

    # 注：ratio 字段（private_card_ratio, tax_burden_deviation 等）使用 float，
    # 因其本身就是归一化的比率/分数，不涉及货币精度。


@dataclass
class ProfileResult:
    """心理画像结果"""
    control_desire_score: int = 0                    # 掌控欲得分 0-100
    loss_aversion_score: int = 0                     # 损失厌恶得分 0-100
    optimism_bias_score: int = 0                     # 乐观偏差得分 0-100
    control_illusion_score: int = 0                  # 控制错觉得分 0-100
    short_termism_score: int = 0                     # 短期主义得分 0-100
    defensiveness_score: int = 0                     # 防御心理得分 0-100
    deviation_index: float = 0.0                     # 综合偏差指数 0-100
    dominant_biases: list[str] = field(default_factory=list)  # 主导偏差类型
    intervention_strategy: dict[str, str] = field(default_factory=dict)  # 干预策略
    business_narrative: str = ""                     # 商业语言叙述
    technical_summary: dict[str, Any] = field(default_factory=dict)  # 技术语言摘要
    peer_average: dict[str, int] = field(default_factory=dict)  # 同行业同规模企业各维度平均分


def _classify_level(score: int) -> str:
    """将分数分类为 high/medium/low。阈值：>70=高风险模式, 50-70=中等, <50=相对理性"""
    if score > 70:
        return "high"
    elif score >= 50:
        return "medium"
    return "low"


def _score_control_desire(data: BehavioralData) -> int:
    """
    评估掌控欲。

    规则：
      - 私卡占比越高，掌控欲越强
      - 小微企业主更容易产生"我的钱我做主"心理
      - 高新技术企业因税收优惠更愿意合规，掌控欲得分可下调

    Args:
        data: 企业行为数据

    Returns:
        掌控欲得分 (0-100 整数)
    """
    if data.private_card_ratio <= 0:
        return 0

    base = int(round(data.private_card_ratio * 100))
    # 小微企业加成（"我的钱我做主"心理更强）
    if data.is_small_micro:
        base = min(100, base + 15)
    # 高新技术企业减成（税收优惠降低私卡动机）
    if data.is_high_tech:
        base = max(0, base - 20)
    return min(100, base)


def _score_loss_aversion(data: BehavioralData) -> int:
    """
    评估损失厌恶。

    规则：
      - 税负率偏离行业越大，说明老板越厌恶纳税"损失"，避税动机越强
      - 偏差 > 3 个百分点 = 极度损失厌恶 → 90+
      - 偏差 1-3 个百分点 = 中等损失厌恶 → 40-70
      - 偏差 < 1 个百分点 = 正常范围 → 0-30

    Args:
        data: 企业行为数据

    Returns:
        损失厌恶得分 (0-100 整数)
    """
    deviation = data.tax_burden_deviation
    if deviation <= 0:
        return 0
    if deviation <= 0.5:
        return int(round(deviation * 40))
    elif deviation <= 1.5:
        return int(round(20 + (deviation - 0.5) * 40))
    elif deviation <= 3.0:
        return int(round(60 + (deviation - 1.5) * 20))
    else:
        return min(100, int(round(90 + (deviation - 3.0) * 3)))


def _score_optimism_bias(data: BehavioralData) -> int:
    """
    评估乐观偏差。

    规则：
      - 历史风险次数越多但整改率低 → 盲目乐观（觉得不会被查到）
      - 连续高风险期数多 → 长期处于风险却不改变 → 高度乐观偏差
      - 风险复发率高 → 重复犯同样错误 → 乐观偏差叠加

    Args:
        data: 企业行为数据

    Returns:
        乐观偏差得分 (0-100 整数)
    """
    score = 0
    # 历史风险计数
    if data.historical_risk_count >= 5:
        score += 40
    elif data.historical_risk_count >= 3:
        score += 25
    elif data.historical_risk_count >= 1:
        score += 10

    # 连续高风险期
    if data.consecutive_high_risk_periods >= 4:
        score += 40
    elif data.consecutive_high_risk_periods >= 2:
        score += 20
    elif data.consecutive_high_risk_periods >= 1:
        score += 5

    # 风险复发率
    if data.risk_recurrence_rate > 0.7:
        score += 25
    elif data.risk_recurrence_rate > 0.4:
        score += 15
    elif data.risk_recurrence_rate > 0.1:
        score += 5

    return min(100, score)


def _score_control_illusion(data: BehavioralData) -> int:
    """
    评估控制错觉。

    规则：
      - 四流匹配度越低 → 业务流程混乱但仍在经营 → 以为能控制局面
      - 匹配度 < 40 → 极度控制错觉
      - 匹配度 40-70 → 中等
      - 匹配度 > 70 → 正常

    Args:
        data: 企业行为数据

    Returns:
        控制错觉得分 (0-100 整数)
    """
    score = 100.0 - float(data.four_flow_match_score)
    return min(100, int(round(score)))


def _score_short_termism(data: BehavioralData) -> int:
    """
    评估短期主义。

    规则：
      - 未申报收入占比反映"先拿到钱再说"的短期思维
      - 占比 > 50% → 极端短期主义
      - 占比 20-50% → 明显短期主义
      - 小微企业无申报收入但有私卡流水 → 高度短期主义

    Args:
        data: 企业行为数据

    Returns:
        短期主义得分 (0-100 整数)
    """
    ratio = data.undeclared_revenue_ratio
    if ratio <= 0:
        return 0
    if ratio <= 0.1:
        return int(round(ratio * 300))
    elif ratio <= 0.3:
        return int(round(30 + (ratio - 0.1) * 200))
    elif ratio <= 0.5:
        return int(round(70 + (ratio - 0.3) * 100))
    else:
        return min(100, int(round(90 + (ratio - 0.5) * 50)))


def _score_defensiveness(data: BehavioralData) -> int:
    """
    评估防御心理。

    规则：
      - 整改完成率反映对合规改进的抵触程度
      - 完成率越低，防御心理越强
      - 完成率 0% → 极度防御
      - 完成率 < 30% → 高度防御
      - 完成率 30-60% → 中等防御
      - 完成率 > 60% → 低防御

    Args:
        data: 企业行为数据

    Returns:
        防御心理得分 (0-100 整数)
    """
    rate = float(data.remediation_completion_rate)
    if rate >= 100:
        return 0
    score = 100.0 - rate
    return min(100, int(round(score)))


def _generate_intervention(result: ProfileResult) -> dict[str, str]:
    """生成各维度干预策略"""
    strategies = {}
    bias_map = {
        "control_desire": result.control_desire_score,
        "loss_aversion": result.loss_aversion_score,
        "optimism_bias": result.optimism_bias_score,
        "control_illusion": result.control_illusion_score,
        "short_termism": result.short_termism_score,
        "defensiveness": result.defensiveness_score,
    }
    for bias, score in bias_map.items():
        level = _classify_level(score)
        strategies[bias] = INTERVENTION_STRATEGIES.get(bias, {}).get(level, "")
    return strategies


def _get_combined_bias_narrative(dominant_biases: list[str]) -> str:
    """根据主导偏差组合生成个性化解读"""
    combos = {
        ("optimism_bias", "control_illusion"): (
            "您的决策模式呈现「乐观偏差+控制错觉」组合：既低估被稽查的概率，又高估自身对混乱业务的控制力。"
            "这种组合是金税四期下最高危的心理模式——'既觉得不会被查到，又觉得查到了也能摆平'。"
        ),
        ("optimism_bias", "short_termism"): (
            "您的决策模式呈现「乐观偏差+短期主义」组合：习惯性地优先短期现金流，同时低估长期合规风险。"
            "这种模式在短期内可能带来资金便利，但每一次不合规操作都在为未来埋下隐患。"
        ),
        ("loss_aversion", "control_desire"): (
            "您的决策模式呈现「损失厌恶+掌控欲」组合：对税负极度敏感，习惯通过私卡掌控资金流向。"
            "请理解：合规纳税不是损失，而是对企业和个人未来的保障。"
        ),
        ("control_desire", "defensiveness"): (
            "您的决策模式呈现「掌控欲+防御心理」组合：既想牢牢掌控资金，又对合规建议持抵触态度。"
            "建议从最小的合规步骤开始，逐步建立对外部专业建议的信任。"
        ),
        ("short_termism", "defensiveness"): (
            "您的决策模式呈现「短期主义+防御心理」组合：追求短期利益的同时抗拒外部干预。"
            "这是典型的'幸存者偏差'——过去的侥幸成功强化了不合规的惯性。"
        ),
    }
    sorted_key = tuple(dominant_biases[:2]) if len(dominant_biases) >= 2 else None
    if sorted_key and sorted_key in combos:
        return combos[sorted_key]
    # 反向也尝试
    if sorted_key:
        reversed_key = (sorted_key[1], sorted_key[0])
        if reversed_key in combos:
            return combos[reversed_key]
    return ""


DISCLAIMER = (
    "【免责声明】本心理画像基于行为经济学理论的启发式推断，"
    "通过企业的财税行为数据（私卡比例、税负偏离度、历史风险记录、整改完成率等）推断企业主的认知偏差倾向。"
    "此分析不构成临床心理学诊断，所有得分仅用于财税合规干预参考，"
    "不应作为任何法律、医疗或雇佣决策的依据。"
)


def _generate_narrative(result: ProfileResult, data: BehavioralData) -> str:
    """生成商业语言心理画像叙述"""
    parts = []
    parts.append("═══════════════════════════════════")
    parts.append("  您（企业主）的财税决策心理画像")
    parts.append("═══════════════════════════════════")
    parts.append("")
    parts.append(f"综合偏差指数：{result.deviation_index:.0f} / 100")

    if result.deviation_index > 70:
        parts.append("风险决策模式：高风险决策模式——显著认知偏差影响财税决策")
    elif result.deviation_index >= 50:
        parts.append("风险决策模式：中等风险——存在一定认知偏差，需关注")
    else:
        parts.append("风险决策模式：相对理性——认知偏差在可控范围内")

    if result.dominant_biases:
        names = [BIAS_CN.get(b, b) for b in result.dominant_biases]
        parts.append(f"主导偏差类型：{'、'.join(names)}")
        # 组合解读
        combo = _get_combined_bias_narrative(result.dominant_biases)
        if combo:
            parts.append("")
            parts.append(f"决策模式解读：{combo}")
    parts.append("")

    parts.append("六维得分详情：")
    dims = [
        ("掌控欲", result.control_desire_score, "您对资金流向的自主掌控倾向"),
        ("损失厌恶", result.loss_aversion_score, "对纳税成本的心理抵触程度"),
        ("乐观偏差", result.optimism_bias_score, "低估稽查风险、高估安全概率的倾向"),
        ("控制错觉", result.control_illusion_score, "以为能控制混乱业务流程的认知偏差"),
        ("短期主义", result.short_termism_score, "优先短期利益、忽视长期合规的趋势"),
        ("防御心理", result.defensiveness_score, "对合规改进建议的抗拒程度"),
    ]
    for name, score, desc in dims:
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        level = _classify_level(score)
        level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "")
        parts.append(f"  {level_emoji} {name:<6} {bar} {score:>3}/100  {desc}")

    parts.append("")
    parts.append("═══════════════════════════════════")
    parts.append("  心理干预建议")
    parts.append("═══════════════════════════════════")
    parts.append("")

    if result.dominant_biases:
        for bias in result.dominant_biases[:3]:
            name = BIAS_CN.get(bias, bias)
            strategy = result.intervention_strategy.get(bias, "")
            parts.append(f"◆ {name}：")
            parts.append(f"  {strategy}")
            parts.append("")

    parts.append("")
    parts.append("─" * 40)
    parts.append(DISCLAIMER)

    return "\n".join(parts)


def determine_size_tier(revenue_annual: Decimal | float) -> str:
    """根据年营收判断企业规模梯度"""
    rev = float(revenue_annual)
    if rev > 50_000_000:
        return "large"
    elif rev >= 5_000_000:
        return "medium"
    else:
        return "small"


def lookup_peer_average(industry: str, revenue_annual: Decimal | float) -> dict[str, int]:
    """
    根据企业所属行业和年营收规模，查找对应的六维偏差基准值。

    Args:
        industry: 国民经济行业分类名称（如'制造'、'批发零售'等）
        revenue_annual: 企业年营收（元）

    Returns:
        六维偏差基准字典，若行业或规模未覆盖则返回默认基准。
    """
    benchmarks = _PROFILE_BENCHMARKS.get("benchmarks", {})
    size_tier = determine_size_tier(revenue_annual)

    # 精确匹配行业
    if industry in benchmarks:
        tier_data = benchmarks[industry].get(size_tier)
        if tier_data:
            return dict(tier_data)

    # 行业简写/部分匹配
    for key in benchmarks:
        if industry in key or key in industry:
            tier_data = benchmarks[key].get(size_tier)
            if tier_data:
                return dict(tier_data)

    # 未匹配到行业时的默认基准（全行业中间值）
    return {
        "control_desire": 48,
        "loss_aversion": 45,
        "optimism_bias": 45,
        "control_illusion": 38,
        "short_termism": 48,
        "defensiveness": 42,
    }


def calculate_psychological_profile(
    behavioral_data: BehavioralData,
    industry: str = "",
    revenue_annual: float = 0.0,
) -> ProfileResult:
    """
    计算企业主的心理画像。

    基于企业财税行为数据，推断六种认知偏差程度，输出心理画像报告和干预策略。

    Args:
        behavioral_data: 企业行为数据（私卡比例、税负偏离、历史风险等）

    Returns:
        ProfileResult: 六维偏差得分、偏差指数、主导偏差、干预策略、双语输出

    Edge Cases:
      - 全是正常数据：所有得分接近 0，无主导偏差
      - 极端异常：多个维度逼近 100
      - 缺失数据（默认值）：保守计算，输出偏低保分

    注意：
      本模型基于行为经济学理论推断，不构成临床心理学诊断。
      所有得分仅用于合规干预参考。
    """
    result = ProfileResult()

    # ── 六维评分 ──
    result.control_desire_score = _score_control_desire(behavioral_data)
    result.loss_aversion_score = _score_loss_aversion(behavioral_data)
    result.optimism_bias_score = _score_optimism_bias(behavioral_data)
    result.control_illusion_score = _score_control_illusion(behavioral_data)
    result.short_termism_score = _score_short_termism(behavioral_data)
    result.defensiveness_score = _score_defensiveness(behavioral_data)

    # ── 综合偏差指数 ──
    # 每个维度0-100分，换算为检查清单中的0-15分制：
    #   normalized_score = raw_score / 100 * 15
    #   总范围 = 6 × 15 = 90，归一化到0-100：sum(raw/100*15) / 90 × 100 = sum(raw) / 600 × 100
    #   数学等价于六维平均值（sum/6），上限封顶100
    scores = {
        "control_desire": result.control_desire_score,
        "loss_aversion": result.loss_aversion_score,
        "optimism_bias": result.optimism_bias_score,
        "control_illusion": result.control_illusion_score,
        "short_termism": result.short_termism_score,
        "defensiveness": result.defensiveness_score,
    }
    result.deviation_index = round(min(sum(scores.values()) / 6.0, 100.0), 2)

    # ── 主导偏差（取得分最高的2个偏差作为"主导偏差"） ──
    sorted_biases = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result.dominant_biases = [k for k, v in sorted_biases[:2] if v > 0]

    # ── 干预策略 ──
    result.intervention_strategy = _generate_intervention(result)

    # ── 同行基准（分行业×规模） ──
    result.peer_average = lookup_peer_average(industry, revenue_annual)

    # ── 商业语言叙述 ──
    result.business_narrative = _generate_narrative(result, behavioral_data)

    # ── 技术摘要 ──
    result.technical_summary = {
        "scores": {BIAS_CN.get(k, k): v for k, v in scores.items()},
        "deviation_index": result.deviation_index,
        "dominant_biases": [BIAS_CN.get(b, b) for b in result.dominant_biases],
        "intervention_strategies": {BIAS_CN.get(k, k): v for k, v in result.intervention_strategy.items()},
        "metadata": {
            "model_version": "1.0.0",
            "bias_count": len(result.dominant_biases),
            "highest_bias": BIAS_CN.get(sorted_biases[0][0], sorted_biases[0][0]) if sorted_biases and sorted_biases[0][1] > 0 else None,
            "is_high_tech": behavioral_data.is_high_tech,
            "is_small_micro": behavioral_data.is_small_micro,
        },
    }

    return result
