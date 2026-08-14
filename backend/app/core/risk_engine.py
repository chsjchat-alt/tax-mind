"""
风险识别规则引擎

基于金税四期稽查逻辑，通过硬编码规则识别企业财税合规风险。

风险维度（7条规则）：
  1. 四流匹配风险（合同-发票-资金-货物）
  2. 私卡收款风险（>30%高风险；大额公转私>50000元/笔>10笔高危）
  3. 成本费用率偏离风险（>30%高风险）
  4. 税负率偏离风险（<行业50%且无优惠=高危）
  5. 进销项匹配风险（匹配率<0.3高风险）
  6. 申报-资金差异风险
  7. 一票否决规则：任意单维度high时总体至少medium

商业语言输出：每个维度的detail字段用商业语言、technical_detail用技术语言
技术语言输出：结构化评分，供后续模块消费
"""

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Any

from app.core.four_flow_match import FourFlowMatchResult, calculate_four_flow_match
from app.core.credit_veto import resolve_tax_credit_veto

# ── 加载行业锚点数据 ──
import json
from pathlib import Path

_BENCHMARKS_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "industry_benchmarks.json"
)


def _load_industry_benchmarks() -> dict[str, dict]:
    """加载行业基准数据 JSON 并构建按行业名索引的字典。"""
    try:
        with open(_BENCHMARKS_PATH, "r", encoding="utf-8-sig") as f:
            data = json.loads(f.read())
        industries = data.get("industries")
        if not isinstance(industries, dict):
            raise ValueError(f"industries 字段应为 dict，实际类型: {type(industries)}")
        return industries
    except Exception as e:
        import warnings
        warnings.warn(f"无法加载行业基准数据 {_BENCHMARKS_PATH}: {e}")
        return {}

INDUSTRY_BENCHMARKS = _load_industry_benchmarks()

# ── 风险等级阈值 ──
RISK_HIGH_THRESHOLD = 70      # 综合风险分 >= 70 时为高风险
RISK_MEDIUM_THRESHOLD = 40    # 综合风险分 >= 40 时为中风险

# ── 各维度风险权重 ──
RISK_WEIGHTS = {
    "four_flow_match": 0.30,                # 四流匹配
    "private_card_ratio": 0.20,             # 私卡收款占比
    "large_personal_transfer": 0.05,        # 大额公转私
    "cost_deviation": 0.15,                 # 成本费用率偏离
    "tax_burden_deviation": 0.15,           # 税负率偏离
    "invoice_bank_mismatch": 0.05,          # 发票-资金差异
    "input_output_imbalance": 0.10,         # 进销项失衡
}

# ── 行业税负率参考值（百分比） ──
INDUSTRY_TAX_BURDEN_REFERENCE = {
    "批发零售": 3.5,
    "制造": 3.5,
    "建筑": 3.5,
    "电商": 1.2,
    "餐饮服务": 2.0,
}

# ── 行业成本费用率参考值（百分比） ──
INDUSTRY_COST_RATE_REFERENCE = {
    "批发零售": 95.0,
    "制造": 85.0,
    "建筑": 90.0,
    "电商": 80.0,
    "餐饮服务": 75.0,
}

# ── 行业私卡占比均值参考（百分比） ──
# 从 industry_benchmarks.json 动态提取，保留空字典作为兜底
_default_private_card_mean = 8.0  # 全行业默认锚点


def _get_private_card_mean(industry_name: str) -> float:
    """获取行业的私卡占比均值锚点（百分比形式）。
    
    industry_benchmarks.json 中 private_card_ratio_mean 以小数存储（如 0.08 = 8%），
    此处转换为百分比返回。
    """
    bm = INDUSTRY_BENCHMARKS.get(industry_name, {})
    decimal_value = bm.get("private_card_ratio_mean", _default_private_card_mean / 100)
    # JSON 中为小数（0.08），转换为百分比（8.0）；若是百分比（>1）则直接使用
    if decimal_value < 1.0:
        return float(decimal_value) * 100
    return float(decimal_value)


# ── 各维度法规依据（policy_ref 条文索引 / policy_basis 条文说明） ──
POLICY_REFERENCES: dict[str, dict[str, str]] = {
    "four_flow_match": {
        "policy_ref": "《国家税务总局关于加强增值税征收管理若干问题的通知》（国税发〔1995〕192号）第一条第（三）项",
        "risk_reason": "合同、发票、资金、货物流之间存在不一致，进项税额抵扣可能不被认可",
        "policy_basis": (
            "纳税人购进货物或应税劳务、支付运输费用，所支付款项的单位，必须与开具抵扣凭证的销货单位、"
            "提供劳务的单位一致，方可申报抵扣进项税额。四流不一致将导致进项税额抵扣被否认，"
            "并可能被认定为虚开发票。"
        ),
    },
    "private_card_ratio": {
        "policy_ref": "《中华人民共和国税收征收管理法》第六十三条",
        "risk_reason": "经营收入通过个人账户收取而未纳入申报收入，涉嫌隐匿收入偷逃税款",
        "policy_basis": (
            "纳税人伪造、变造、隐匿、擅自销毁账簿、记账凭证，或者在账簿上多列支出或者不列、少列收入，"
            "或者经税务机关通知申报而拒不申报或者进行虚假的纳税申报，不缴或者少缴应纳税款的，是偷税。"
            "对纳税人偷税的，由税务机关追缴其不缴或者少缴的税款、滞纳金，并处不缴或者少缴的税款"
            "百分之五十以上五倍以下的罚款。"
        ),
    },
    "large_personal_transfer": {
        "policy_ref": "《金融机构大额交易和可疑交易报告管理办法》（中国人民银行令〔2016〕第3号）第八条",
        "risk_reason": "存在多笔大额公转私交易，资金流向个人账户，可能用于转移应税收入",
        "policy_basis": (
            "当日单笔或者累计交易人民币5万元以上（含5万元）的现金收付属于应当报告的大额交易。"
            "大额公转私若无真实经营背景，可能构成转移应税收入、逃避缴纳税款，"
            "并触发反洗钱监测与税务稽查。"
        ),
    },
    "cost_deviation": {
        "policy_ref": "《中华人民共和国企业所得税法》第八条",
        "risk_reason": "成本费用率偏离行业均值，成本列支的真实性与合理性存疑，可能虚列成本",
        "policy_basis": (
            "企业实际发生的与取得收入有关的、合理的支出，包括成本、费用、税金、损失和其他支出，"
            "准予在计算应纳税所得额时扣除。成本费用率异常偏离行业水平时，"
            "成本支出的真实性与合理性存疑。"
        ),
    },
    "tax_burden_deviation": {
        "policy_ref": "《中华人民共和国增值税法》第十四条（原《增值税暂行条例》第四条）",
        "risk_reason": "实际税负率显著低于行业基准，可能隐匿收入或虚增进项税额",
        "policy_basis": (
            "按照一般计税方法计算缴纳增值税的，应纳税额为当期销项税额抵扣当期进项税额后的余额。"
            "税负率明显低于行业水平且无正当理由时，存在隐匿收入、虚增进项税额抵扣的嫌疑。"
        ),
    },
    "input_output_imbalance": {
        "policy_ref": "《中华人民共和国发票管理办法》第二十一条、第三十五条",
        "risk_reason": "进销项发票品名对应关系异常，涉嫌虚开发票或隐匿未开票收入",
        "policy_basis": (
            "任何单位和个人不得为他人、为自己开具与实际经营业务情况不符的发票，"
            "或者让他人为自己开具与实际经营业务情况不符的发票。"
            "虚开发票的，由税务机关没收违法所得，虚开金额超过1万元的并处5万元以上50万元以下的罚款；"
            "构成犯罪的，依法追究刑事责任。"
        ),
    },
    "invoice_bank_mismatch": {
        "policy_ref": "《中华人民共和国税收征收管理法》第十九条",
        "risk_reason": "发票金额与银行资金流水不一致，账实不符，业务凭证支撑不足",
        "policy_basis": (
            "纳税人、扣缴义务人应当按照规定设置账簿，根据合法、有效凭证记账、核算。"
            "发票金额与银行资金流水不一致，说明账实不符，相关业务缺乏合法有效的凭证支撑。"
        ),
    },
}


def _with_policy_basis(key: str, base: dict, flags: list[str]) -> dict:
    """合并风险成因与法规依据字段到维度详情。

    为每个维度补充三类信息：
      - risk_reason: 本次评估的风险成因（优先取风险标记，无则用该维度通用成因）
      - policy_ref:  所依据的税法条文索引（如《增值税法》第十四条）
      - policy_basis: 政策依据条文说明
    """
    policy = POLICY_REFERENCES.get(key, {})
    reason = flags[0] if flags else policy.get("risk_reason", "")
    return {
        **base,
        "risk_reason": reason,
        "policy_ref": policy.get("policy_ref", ""),
        "policy_basis": policy.get("policy_basis", ""),
    }


@dataclass
class EnterpriseRiskInput:
    """风险引擎输入数据结构"""
    enterprise_name: str
    industry: str                                    # 行业类型
    revenue_annual: Decimal                          # 年营收
    tax_rate_industry: Decimal                       # 行业平均税负率 (%)
    cost_rate_industry: Decimal                      # 行业平均成本费用率 (%)
    actual_tax_burden_rate: Decimal                  # 实际税负率 (%)
    actual_cost_rate: Decimal                        # 实际成本费用率 (%)
    total_private_card_amount: Decimal               # 私卡收款总额
    total_revenue: Decimal                           # 申报收入总额
    total_input_invoice: Decimal                     # 进项税额合计
    total_output_invoice: Decimal                    # 销项税额合计
    # ── 一票否决输入（纳税信用 / 涉税犯罪）──
    tax_credit_level: str | None = None              # 纳税信用等级 A/B/C/D（None=未评级）
    tax_crime_convicted: bool = False                # 涉税犯罪生效判决


@dataclass
class RiskAssessmentResult:
    """风险评估结果"""
    overall_risk_level: str = "low"                  # low / medium / high
    overall_risk_score: float = 0.0                  # 总体风险评分 0-100
    dimension_scores: dict[str, float] = field(default_factory=dict)
    dim_details: dict[str, dict] = field(default_factory=dict)  # 各维度双语详情
    risk_flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    business_narrative: str = ""                     # 商业语言叙述
    technical_summary: dict[str, Any] = field(default_factory=dict)


def _assess_private_card_risk(
    private_amount: Decimal, total_revenue: Decimal,
    industry_mean: float = 8.0,
) -> tuple[float, list[str], list[str]]:
    """
    评估私卡收款风险（行业锚点法）。

    以行业 private_card_ratio_mean 为锚点，计算超额偏离：
      excess = actual_ratio - industry_mean

    不同行业的私卡正常水平差异显著：
      - 餐饮服务: 15% 为常态（大量现金/个人收款）
      - 批发零售: 8%  为常态
      - 电商:      8%  为常态

    Args:
        private_amount: 私卡收款总额
        total_revenue: 申报收入总额
        industry_mean: 行业私卡占比均值（百分比），默认 8%

    Returns:
        (风险分 0-100, 风险标记列表, 整改建议列表)
    """
    anchor = industry_mean / 100.0  # 百分比 → 小数

    if total_revenue <= Decimal("0"):
        if private_amount > Decimal("0"):
            return 80.0, ["存在私卡收款但无申报收入"], ["停止私卡收款，将所有收入纳入对公账户并如实申报"]
        return 0.0, [], []

    ratio = float(private_amount / total_revenue)
    excess = ratio - anchor  # 超出行业均值的部分

    if excess <= 0:
        # 不超出行业均值 → 正常
        return round(max(0, ratio * 100), 1), [], []
    elif excess <= 0.05:
        # 略高于行业均值
        return round(excess * 400, 1), [], []
    elif excess <= 0.15:
        return round(20 + (excess - 0.05) * 350, 1), \
            [f"私卡收款占比 {ratio:.1%}，超出行业均值 {anchor:.1%} 约 {excess:.1%}，处于异常水平"], \
            ["逐步减少私卡收款，将经营收入转入对公账户"]
    elif excess <= 0.25:
        return round(55 + (excess - 0.15) * 250, 1), \
            [f"私卡收款占比 {ratio:.1%}，大幅超出行业均值 {anchor:.1%}（超出 {excess:.1%}），涉嫌隐匿收入"], \
            ["立即停止私卡收款，补申报相应收入，建立对公账户管理制度"]
    else:
        return min(100.0, round(80 + (excess - 0.25) * 100, 1)), \
            [f"私卡收款占比 {ratio:.1%}，严重超出行业均值 {anchor:.1%}（超出 {excess:.1%}），属于严重税务违规"], \
            ["立即将所有经营收入转入对公账户，聘请税务师进行自查补税"]


def _assess_cost_deviation_risk(
    actual_rate: Decimal, industry_rate: Decimal
) -> tuple[float, list[str], list[str]]:
    """
    评估成本费用率偏离风险。

    Args:
        actual_rate: 实际成本费用率 (%)
        industry_rate: 行业平均成本费用率 (%)

    Returns:
        (风险分, 风险标记, 整改建议)
    """
    if industry_rate <= Decimal("0"):
        return 0.0, [], []

    deviation = abs(float(actual_rate - industry_rate))
    if deviation <= 5.0:
        return 0.0, [], []
    elif deviation <= 15.0:
        return round(deviation * 2, 1), \
            [f"成本费用率偏离行业均值 {deviation:.1f}个百分点"], \
            ["核实成本费用列支是否真实、合理"]
    elif deviation <= 30.0:
        return round(30 + (deviation - 15) * 3, 1), \
            [f"成本费用率严重偏离行业均值 {deviation:.1f}个百分点，可能存在虚列成本"], \
            ["审查成本费用明细，确保所有支出有真实业务支撑和合法凭证"]
    else:
        return min(100.0, round(75 + (deviation - 30) * 2, 1)), \
            [f"成本费用率异常偏离行业均值 {deviation:.1f}个百分点，虚列成本嫌疑极高"], \
            ["立即进行成本费用全面核查，重点排查无票支出、虚假发票、关联交易"]


def _assess_tax_burden_risk(
    actual_rate: Decimal, industry_rate: Decimal,
    has_preference: bool = False,
) -> tuple[float, list[str], list[str], bool]:
    """
    评估税负率偏离风险。

    税负率过低（远低于行业平均值）是金税四期重点稽查方向。
    特别规则：税负率 < 行业50% 且无税收优惠 → 高危。

    Args:
        actual_rate: 实际税负率 (%)
        industry_rate: 行业平均税负率 (%)
        has_preference: 是否享受税收优惠

    Returns:
        (风险分, 风险标记, 整改建议, 是否为高危)
    """
    is_severe = False
    if industry_rate <= Decimal("0"):
        return 0.0, [], [], is_severe

    # 税负率<行业50%且无优惠 → 直接高危
    half_industry = industry_rate * Decimal("0.5")
    if actual_rate < half_industry and not has_preference:
        return 85.0, \
            [f"税负率严重偏低：实际 {actual_rate}% < 行业 {industry_rate}% 的50% ({half_industry}%)，且无税收优惠解释"], \
            ["立即自查是否存在隐匿收入、虚增进项等行为，必要时主动补税并申请税收优惠"], \
            True

    deviation = float(industry_rate - actual_rate)
    if deviation <= 0.3:
        return 0.0, [], [], is_severe
    elif deviation <= 1.0:
        return round(deviation * 30, 1), \
            [f"税负率低于行业均值 {deviation:.1f}个百分点"], \
            ["关注税负率偏低原因，确保增值税进项抵扣合规"], \
            is_severe
    elif deviation <= 3.0:
        return round(30 + (deviation - 1) * 25, 1), \
            [f"税负率明显偏低，低于行业均值 {deviation:.1f}个百分点，为税务稽查重点指标"], \
            ["自查是否存在隐匿收入、虚增进项等问题"], \
            is_severe
    else:
        return min(100.0, round(80 + (deviation - 3) * 10, 1)), \
            [f"税负率严重偏低，低于行业均值 {deviation:.1f}个百分点，触发稽查预警"], \
            ["全面自查企业收入、成本、进项税额的真实性，必要时主动补税"], \
            True


def _assess_product_matching(
    product_match_score: float,
) -> tuple[float, list[str], list[str]]:
    """
    评估进销项品名匹配风险（基于 Jaccard 相似度严格匹配）。

    替换旧版随机概率法（税金额比值阈值 0.6/1.4），
    改为基于商品名称集合交并集（Jaccard 相似度）的严格匹配。

    Args:
        product_match_score: 进销商品名 Jaccard 匹配度（0-100，四流匹配模块计算）

    Returns:
        (风险分 0-100, 风险标记列表, 整改建议列表)
    """
    jaccard = product_match_score / 100.0  # 归一化到 0-1

    risk_score = round((1.0 - jaccard) * 100, 2)

    if jaccard >= 0.6:
        return risk_score if risk_score > 0 else 0.0, [], []
    elif jaccard >= 0.3:
        return risk_score, \
            [f"进销项品名 Jaccard 匹配度 {jaccard:.0%}（偏低），进项产品与销项产品对应关系可疑"], \
            ["关注进销项发票品名对应关系，确保采购与销售产品逻辑一致"]
    else:
        return risk_score, \
            [f"进销项品名 Jaccard 匹配度 {jaccard:.0%}（极低），进项与销项产品几乎无交集，"
             "可能存在进销发票品名不一致或隐匿收入"], \
            ["核查进销项发票品名一致性，排查是否存在虚开发票或隐匿未开票收入"]


def _assess_input_output_balance(
    input_total: Decimal, output_total: Decimal
) -> tuple[float, list[str], list[str]]:
    """
    评估进销项税额平衡度。

    Args:
        input_total: 进项税额合计
        output_total: 销项税额合计

    Returns:
        (风险分, 风险标记, 整改建议)
    """
    if output_total <= Decimal("0") and input_total <= Decimal("0"):
        return 0.0, [], []
    if output_total <= Decimal("0"):
        return 70.0, ["有进项发票但无销项，可能存在隐匿收入"], ["核实是否存在未开票收入未申报"]

    ratio = float(input_total / output_total)
    if 0.6 <= ratio <= 1.4:
        return 0.0, [], []
    elif ratio < 0.6:
        return round((0.6 - ratio) * 100, 1), \
            [f"进销比偏低 ({ratio:.2f})，可能存在虚开风险"], \
            ["核实销项发票的真实性，确保进项发票取得及时"]
    else:
        return min(100.0, round((ratio - 1.4) * 80, 1)), \
            [f"进销比偏高 ({ratio:.2f})，进项异常增加"], \
            ["审查进项发票的合规性，排查虚增进项抵扣"]


def _assess_large_personal_transfer(
    bank_transactions: list | None,
) -> tuple[float, list[str], list[str]]:
    """
    评估大额公转私风险。

    规则：公转私>50000元/笔 且 ≥10笔 → 高风险

    Args:
        bank_transactions: 银行流水列表

    Returns:
        (风险分, 风险标记, 整改建议)
    """
    if not bank_transactions:
        return 0.0, [], []

    large_count = 0
    for tx in bank_transactions:
        try:
            amt = tx.amount if hasattr(tx, 'amount') else Decimal(str(tx.get('amount', 0)))
            acct_type = tx.account_type if hasattr(tx, 'account_type') else tx.get('account_type', '')
            direction = tx.direction if hasattr(tx, 'direction') else tx.get('direction', '')
        except Exception:
            continue
        if (acct_type == "personal" and direction == "outflow" and
                float(amt) > 50000.0):
            large_count += 1

    if large_count >= 10:
        return 80.0, \
            [f"大额公转私交易 {large_count} 笔（>50000元/笔），涉嫌私卡转移资金"], \
            ["审查所有公转私交易的业务实质，确保每笔有真实业务背景和合法凭证"]
    elif large_count >= 5:
        return round(large_count * 5, 1), \
            [f"存在 {large_count} 笔大额公转私交易（>50000元/笔），需关注"], \
            ["核实公转私交易是否与真实采购、工资、分红等对应"]
    elif large_count > 0:
        return round(large_count * 2, 1), [], []
    return 0.0, [], []


def assess_enterprise_risk(
    enterprise_input: EnterpriseRiskInput,
    flow_match_result: FourFlowMatchResult | None = None,
    contracts: list | None = None,
    invoices: list | None = None,
    bank_transactions: list | None = None,
    has_tax_preference: bool = False,
    config: dict | None = None,
) -> RiskAssessmentResult:
    """
    企业财税合规风险评估主入口。

    综合七个维度进行风险评估，包含一票否决规则，输出双语结果。

    Args:
        enterprise_input: 企业风险输入数据
        flow_match_result: 已有四流匹配结果（可选）
        contracts: 合同记录列表
        invoices: 发票记录列表
        bank_transactions: 银行流水列表
        has_tax_preference: 是否享受税收优惠（影响税负率判定）
        config: 参数配置（B1 配置化；None 时使用模块内权威默认值）。
                支持键：risk_high_threshold / risk_medium_threshold /
                high_dimension_score_threshold / weights_7dim

    Returns:
        RiskAssessmentResult: 包含风险等级、得分、标记、建议、双语输出
    """
    # ── B1 参数配置化：读取阈值与权重（未配置回退模块默认值）──
    if config is None:
        high_threshold = RISK_HIGH_THRESHOLD
        medium_threshold = RISK_MEDIUM_THRESHOLD
        high_dim_threshold = 70.0
        weights = RISK_WEIGHTS
    else:
        high_threshold = (
            config.get("risk_high_threshold", RISK_HIGH_THRESHOLD)
            if config.get("risk_high_threshold") is not None
            else RISK_HIGH_THRESHOLD
        )
        medium_threshold = (
            config.get("risk_medium_threshold", RISK_MEDIUM_THRESHOLD)
            if config.get("risk_medium_threshold") is not None
            else RISK_MEDIUM_THRESHOLD
        )
        high_dim_threshold = (
            config.get("high_dimension_score_threshold", 70.0)
            if config.get("high_dimension_score_threshold") is not None
            else 70.0
        )
        weights = config.get("weights_7dim", RISK_WEIGHTS) or RISK_WEIGHTS

    result = RiskAssessmentResult()

    # ── 边界条件：空数据 ──
    has_data = (
        enterprise_input.total_revenue > Decimal("0") or
        enterprise_input.total_private_card_amount > Decimal("0") or
        (flow_match_result is not None and flow_match_result.overall_score < 100) or
        (contracts and invoices and bank_transactions)
    )
    if not has_data:
        # 数据不足时，纳税信用 D 级 / 涉税犯罪仍为直接判级（2025 年第 12 号）
        insufficient_veto = resolve_tax_credit_veto(
            enterprise_input.tax_credit_level,
            enterprise_input.tax_crime_convicted,
        )
        if insufficient_veto:
            result.overall_risk_score = 100.0
            result.overall_risk_level = "high"
            result.risk_flags.append(insufficient_veto)
            result.business_narrative = (
                f"「{enterprise_input.enterprise_name}」{insufficient_veto}，"
                "即使暂缺经营数据，风险等级仍直接判为最高。"
            )
            result.technical_summary = {
                "status": "veto_triggered",
                "reason": insufficient_veto,
                "overall_score": 100.0,
                "risk_level": "high",
                "tax_credit_veto": insufficient_veto,
            }
        else:
            result.business_narrative = "暂无足够经营数据用于风险评估，请补充企业财务数据。"
            result.technical_summary = {"status": "insufficient_data"}
        return result

    # ── 四流匹配计算 ──
    if flow_match_result is None:
        from app.core.four_flow_match import ContractRecord, InvoiceRecord, BankTransactionRecord
        flow_match_result = calculate_four_flow_match(
            contracts or [], invoices or [], bank_transactions or [],
        )

    # ── 各维度风险评估 ──
    dim_details = {}  # 每维度双语详情

    # 维度 1：四流匹配风险
    ffm_risk = 100.0 - float(flow_match_result.overall_score)
    dim_details["four_flow_match"] = _with_policy_basis(
        "four_flow_match",
        {
            "score": ffm_risk,
            "detail": f"四流匹配度 {flow_match_result.overall_score:.0f} 分——合同、发票、资金、货物的一致性",
            "technical_detail": f"综合得分={flow_match_result.overall_score:.0f}，合同发票匹配={flow_match_result.contract_invoice_score:.0f}，发票资金匹配={flow_match_result.invoice_bank_score:.0f}，对手一致性={flow_match_result.counterparty_consistency_score:.0f}，金额一致性={flow_match_result.amount_consistency_score:.0f}，品名匹配={flow_match_result.product_match_score:.0f}",
        },
        flow_match_result.risk_flags if ffm_risk > 0 else [],
    )
    if ffm_risk > 0:
        result.risk_flags.extend(flow_match_result.risk_flags)

    # 维度 2：私卡收款风险（行业锚点法）
    industry_mean = _get_private_card_mean(enterprise_input.industry)
    priv_score, priv_flags, priv_recs = _assess_private_card_risk(
        enterprise_input.total_private_card_amount,
        enterprise_input.total_revenue,
        industry_mean=industry_mean,
    )
    dim_details["private_card_ratio"] = _with_policy_basis(
        "private_card_ratio",
        {
            "score": priv_score,
            "detail": f"私卡收款占总收入 {float(enterprise_input.total_private_card_amount / enterprise_input.total_revenue * 100) if enterprise_input.total_revenue > 0 else 0:.1f}%——行业锚点 {industry_mean:.1f}%（{enterprise_input.industry}），超出即触发风险",
            "technical_detail": f"私卡总额={enterprise_input.total_private_card_amount}元，申报收入={enterprise_input.total_revenue}元，占比={float(enterprise_input.total_private_card_amount / enterprise_input.total_revenue * 100) if enterprise_input.total_revenue > 0 else 0:.1f}%，行业锚点={industry_mean}%，超出幅度={max(0, float(enterprise_input.total_private_card_amount / enterprise_input.total_revenue * 100) if enterprise_input.total_revenue > 0 else 0 - industry_mean):.1f}pp",
        },
        priv_flags,
    )
    result.risk_flags.extend(priv_flags)
    result.recommendations.extend(priv_recs)

    # 维度 3：大额公转私风险（新增第7条规则）
    lpt_score, lpt_flags, lpt_recs = _assess_large_personal_transfer(bank_transactions)
    dim_details["large_personal_transfer"] = _with_policy_basis(
        "large_personal_transfer",
        {
            "score": lpt_score,
            "detail": "大额公转私交易检测——公转私>50000元/笔且≥10笔视为高风险",
            "technical_detail": f"风险评分={lpt_score}，可疑交易笔数={len(lpt_flags)}",
        },
        lpt_flags,
    )
    result.risk_flags.extend(lpt_flags)
    result.recommendations.extend(lpt_recs)

    # 维度 4：成本费用率偏离风险
    cost_score, cost_flags, cost_recs = _assess_cost_deviation_risk(
        enterprise_input.actual_cost_rate,
        enterprise_input.cost_rate_industry or
        Decimal(str(INDUSTRY_COST_RATE_REFERENCE.get(enterprise_input.industry, 85.0))),
    )
    dim_details["cost_deviation"] = _with_policy_basis(
        "cost_deviation",
        {
            "score": cost_score,
            "detail": f"成本费用率 {enterprise_input.actual_cost_rate}% vs 行业 {enterprise_input.cost_rate_industry or Decimal(str(INDUSTRY_COST_RATE_REFERENCE.get(enterprise_input.industry, 85.0)))}%——偏离度越大虚列成本嫌疑越高",
            "technical_detail": f"实际成本率={enterprise_input.actual_cost_rate}%，行业基准={enterprise_input.cost_rate_industry or INDUSTRY_COST_RATE_REFERENCE.get(enterprise_input.industry, 85.0)}%，偏离={abs(float(enterprise_input.actual_cost_rate - (enterprise_input.cost_rate_industry or Decimal(str(INDUSTRY_COST_RATE_REFERENCE.get(enterprise_input.industry, 85.0)))))):.1f}pp",
        },
        cost_flags,
    )
    result.risk_flags.extend(cost_flags)
    result.recommendations.extend(cost_recs)

    # 维度 5：税负率偏离风险
    tax_score, tax_flags, tax_recs, tax_severe = _assess_tax_burden_risk(
        enterprise_input.actual_tax_burden_rate,
        enterprise_input.tax_rate_industry or
        Decimal(str(INDUSTRY_TAX_BURDEN_REFERENCE.get(enterprise_input.industry, 2.0))),
        has_preference=has_tax_preference,
    )
    dim_details["tax_burden_deviation"] = _with_policy_basis(
        "tax_burden_deviation",
        {
            "score": tax_score,
            "detail": f"税负率 {enterprise_input.actual_tax_burden_rate}% vs 行业 {enterprise_input.tax_rate_industry or Decimal(str(INDUSTRY_TAX_BURDEN_REFERENCE.get(enterprise_input.industry, 2.0)))}%——税负率过低是稽查重点指标",
            "technical_detail": f"实际税负率={enterprise_input.actual_tax_burden_rate}%，行业基准={enterprise_input.tax_rate_industry or INDUSTRY_TAX_BURDEN_REFERENCE.get(enterprise_input.industry, 2.0)}%，偏离={float((enterprise_input.tax_rate_industry or Decimal(str(INDUSTRY_TAX_BURDEN_REFERENCE.get(enterprise_input.industry, 2.0)))) - enterprise_input.actual_tax_burden_rate):.1f}pp，享受优惠={has_tax_preference}，严重={tax_severe}",
        },
        tax_flags,
    )
    result.risk_flags.extend(tax_flags)
    result.recommendations.extend(tax_recs)

    # 维度 6：进销项品名匹配（Jaccard 相似度严格匹配 → 替换旧版税金额比值随机概率法）
    io_score, io_flags, io_recs = _assess_product_matching(
        flow_match_result.product_match_score,
    )
    dim_details["input_output_imbalance"] = _with_policy_basis(
        "input_output_imbalance",
        {
            "score": io_score,
            "detail": f"进销项品名 Jaccard 匹配度 {flow_match_result.product_match_score:.0f} 分——"
                      "进项原材料/商品与销项商品名称的一致性",
            "technical_detail": f"进销项Jaccard匹配度={flow_match_result.product_match_score:.2f}，风险评分={io_score:.2f}，方法=Jaccard相似度",
        },
        io_flags,
    )
    result.risk_flags.extend(io_flags)
    result.recommendations.extend(io_recs)

    # 维度 7：发票-资金差异
    ib_mismatch_score = 100.0 - float(flow_match_result.invoice_bank_score)
    dim_details["invoice_bank_mismatch"] = _with_policy_basis(
        "invoice_bank_mismatch",
        {
            "score": ib_mismatch_score,
            "detail": f"发票-银行资金匹配度 {flow_match_result.invoice_bank_score:.0f} 分——发票金额与银行流水是否一致",
            "technical_detail": f"发票资金匹配度={flow_match_result.invoice_bank_score:.0f}，差异风险评分={ib_mismatch_score:.0f}",
        },
        [],
    )

    # ── 写入结果对象 ──
    result.dim_details = dim_details

    # ── 汇总评分 ──
    dimension_scores = {
        "four_flow_match": dim_details["four_flow_match"]["score"],
        "private_card_ratio": dim_details["private_card_ratio"]["score"],
        "large_personal_transfer": dim_details["large_personal_transfer"]["score"],
        "cost_deviation": dim_details["cost_deviation"]["score"],
        "tax_burden_deviation": dim_details["tax_burden_deviation"]["score"],
        "input_output_imbalance": dim_details["input_output_imbalance"]["score"],
        "invoice_bank_mismatch": dim_details["invoice_bank_mismatch"]["score"],
    }
    result.dimension_scores = {k: round(v, 2) for k, v in dimension_scores.items()}

    overall = sum(
        score * weights[dim]
        for dim, score in dimension_scores.items()
    )
    result.overall_risk_score = round(overall, 2)

    # ── 一票否决规则 ──
    high_count = sum(1 for score in dimension_scores.values() if score >= high_dim_threshold)
    if high_count >= 2 and result.overall_risk_score < high_threshold:
        # 2个及以上维度超过阈值 → 提升至高风险
        result.overall_risk_score = high_threshold
    elif high_count >= 1 and result.overall_risk_score < medium_threshold:
        # 1个维度超过阈值 → 至少中等风险
        result.overall_risk_score = medium_threshold

    # ── 一票否决扩展：纳税信用 D 级 / 涉税犯罪（2025 年第 12 号 / 刑法第 201 条）──
    # 触发则风险分强制置顶、且修复加分不计（由 compliance_adjustment 拦截）
    tax_credit_veto_reason = resolve_tax_credit_veto(
        enterprise_input.tax_credit_level,
        enterprise_input.tax_crime_convicted,
    )
    if tax_credit_veto_reason:
        result.overall_risk_score = 100.0
        result.overall_risk_level = "high"
        result.risk_flags.append(tax_credit_veto_reason)
        result.recommendations.append(
            "纳税信用 D 级 / 涉税犯罪为直接判级情形：立即委托税务师与律师制定补缴、"
            "滞纳金与罚款处置方案，依据《纳税缴费信用管理办法》（2025 年第 12 号）"
            "申请纳税缴费信用修复，并保留全部整改凭证以备合规考察。"
        )

    # ── 风险等级判定 ──
    if result.overall_risk_score >= high_threshold:
        result.overall_risk_level = "high"
    elif result.overall_risk_score >= medium_threshold:
        result.overall_risk_level = "medium"
    else:
        result.overall_risk_level = "low"

    # ── 去重 ──
    result.risk_flags = list(dict.fromkeys(result.risk_flags))
    result.recommendations = list(dict.fromkeys(result.recommendations))

    # ── 生成双语输出 ──
    result.business_narrative = _generate_risk_narrative(result, enterprise_input)
    result.technical_summary = {
        "dimension_scores": result.dimension_scores,
        "dimension_details": dim_details,
        "overall_score": result.overall_risk_score,
        "risk_level": result.overall_risk_level,
        "weights": weights,
        "flags_count": len(result.risk_flags),
        "thresholds": {
            "high": high_threshold,
            "medium": medium_threshold,
        },
        "veto_triggered": high_count >= 1,
        "tax_credit_veto": tax_credit_veto_reason,
    }

    return result


def _generate_risk_narrative(result: RiskAssessmentResult, inp: EnterpriseRiskInput) -> str:
    """生成商业语言风险评估叙述"""
    level_map = {"low": "低风险 · 绿色", "medium": "中等风险 · 黄色预警", "high": "高风险 · 红色警报"}
    level = level_map.get(result.overall_risk_level, result.overall_risk_level)

    parts = [
        f"「{inp.enterprise_name}」财税合规风险评估报告",
        f"",
        f"综合风险等级：{level}",
        f"综合风险评分：{result.overall_risk_score:.0f} / 100",
        f"",
    ]

    if result.risk_flags:
        parts.append(f"发现 {len(result.risk_flags)} 个风险点：")
        for i, flag in enumerate(result.risk_flags[:8], 1):
            parts.append(f"  {i}. {flag}")
    else:
        parts.append("未发现明显财税合规风险，经营状况良好。")

    if result.recommendations:
        parts.append("")
        parts.append("整改建议：")
        for i, rec in enumerate(result.recommendations[:5], 1):
            parts.append(f"  {i}. {rec}")

    return "\n".join(parts)
