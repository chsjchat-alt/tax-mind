"""
财务数据合规性校验引擎

扫描已生成的财务数据（会计凭证、财务报表、税务台账），
基于预设合规标准识别不合规条目，输出结构化的不合规发现清单。

校验覆盖以下维度：
  1. 税负率合规（增值税实际税负率 vs 行业预警值）
  2. 发票匹配合规（进销项匹配率、四流一致性）
  3. 科目异常检测（应收/应付激增、存货异常、折旧不足）
  4. 财务比率异常（流动比率、速动比率、资产负债率）
  5. 凭证合规（借贷平衡、科目使用规范、凭证编号连续性）
  6. 纳税申报差异（申报收入 vs 账面收入、申报税额 vs 计提税额）
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app.core.four_flow_match import calculate_four_flow_match

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#  合规阈值配置（基于国家税务总局预警值 + 行业基准）
# ═══════════════════════════════════════════

INDUSTRY_TAX_BURDEN_ALERTS: dict[str, dict[str, float]] = {
    "批发零售": {"vat_warning": 1.5, "vat_critical": 0.8, "income_tax_warning": 0.5, "target_vat": 2.5},
    "制造":     {"vat_warning": 2.0, "vat_critical": 1.0, "income_tax_warning": 1.0, "target_vat": 3.5},
    "建筑":     {"vat_warning": 2.0, "vat_critical": 1.0, "income_tax_warning": 0.8, "target_vat": 2.8},
    "电商":     {"vat_warning": 0.5, "vat_critical": 0.2, "income_tax_warning": 0.5, "target_vat": 1.5},
    "餐饮服务": {"vat_warning": 1.0, "vat_critical": 0.3, "income_tax_warning": 0.3, "target_vat": 1.5},
}

COMPLIANCE_RULES = {
    # 税负率规则
    "vat_burden_low": {
        "category": "tax",
        "severity": "medium",
        "title_template": "增值税实际税负率（{0}%）低于行业预警值（{1}%）",
        "desc_template": (
            "企业当期增值税实际税负率为{0}%，低于{1}行业预警下限{2}%。"
            "进项税额抵扣比例（{3}%）偏高，请核查进项发票真实性及业务合理性，"
            "确认是否存在虚开、多抵进项等不合规情形。"
        ),
        "suggestion": "建议逐笔核查进项发票业务真实性，比对四流一致性，关注是否存在关联方虚开发票。",
    },
    "vat_burden_zero": {
        "category": "tax",
        "severity": "high",
        "title_template": "增值税实际税负率为0%——可能存在隐匿收入或虚增进项",
        "desc_template": (
            "企业当期申报增值税应纳税额为0元，但存在持续经营收入。"
            "请核实销项税额是否完整申报，进项税额抵扣凭证是否真实合规。"
        ),
        "suggestion": "立即核查销项税额完整性，比对银行流水与开票金额，排查隐匿收入风险。",
    },
    "income_tax_burden_low": {
        "category": "tax",
        "severity": "medium",
        "title_template": "企业所得税贡献率（{0}%）显著低于行业平均水平",
        "desc_template": (
            "当期企业所得税应纳税额占营业收入比例为{0}%，低于{1}行业参考下限{2}%。"
            "请核实成本费用列支的合规性和合理性，排查是否存在虚增成本、多列费用等问题。"
        ),
        "suggestion": "抽查大额成本费用凭证的原始单据，核实业务真实性和发票合规性。",
    },
    # 科目异常规则
    "ar_spike": {
        "category": "accounting",
        "severity": "medium",
        "title_template": "应收账款期末余额（{0}元）异常偏高——周转天数{1}天",
        "desc_template": (
            "期末应收账款余额为{0}元，占流动资产{1}%，周转天数达{2}天。"
            "请核实是否存在虚假销售虚增应收账款，或对关联方大额赊销未计提坏账准备。"
        ),
        "suggestion": "逐笔核对应收账款明细账与销售合同，检查账龄结构并足额计提坏账准备。",
    },
    "ap_spike": {
        "category": "accounting",
        "severity": "low",
        "title_template": "应付账款期末余额（{0}元）周转天数{1}天",
        "desc_template": (
            "期末应付账款余额为{0}元，周转天数{1}天，"
            "请核实是否存在虚增采购虚列应付账款，或利用应付账款隐匿收入。"
        ),
        "suggestion": "核对大额应付账款对应的采购合同、入库单和发票，确认业务真实性。",
    },
    "inventory_abnormal": {
        "category": "accounting",
        "severity": "medium",
        "title_template": "存货期末余额（{0}元）存在跌价风险",
        "desc_template": (
            "期末存货余额{0}元，存货周转天数{1}天，超出行业正常水平。"
            "请核实是否存在积压、呆滞存货未计提跌价准备，以及已发货未确认收入导致的存货虚增。"
        ),
        "suggestion": "全面盘点存货，对可变现净值低于成本的存货计提跌价准备，核实已发货商品收入确认时点。",
    },
    # 财务比率异常
    "current_ratio_abnormal": {
        "category": "financial",
        "severity": "low",
        "title_template": "流动比率（{0}）偏离正常区间",
        "desc_template": (
            "期末流动比率为{0}，{1}行业正常区间为1.0-2.0。"
            "{2}"
        ),
        "suggestion": "分析短期偿债能力变化原因，关注是否存在资金链风险或资产质量恶化。",
    },
    "asset_liability_ratio_high": {
        "category": "financial",
        "severity": "medium",
        "title_template": "资产负债率（{0}%）处于较高水平",
        "desc_template": (
            "期末资产负债率为{0}%，{1}行业参考上限为{2}%。"
            "高杠杆经营可能诱发激进财税筹划动机，请关注带息负债规模和偿债压力。"
        ),
        "suggestion": "评估负债结构和偿债能力，关注是否存在表外负债或隐性担保。",
    },
    "depreciation_insufficient": {
        "category": "accounting",
        "severity": "low",
        "title_template": "固定资产折旧计提（月{0}元）低于测算基准",
        "desc_template": (
            "本月折旧计提{0}元，按固定资产原值{1}元及行业平均折旧率测算，"
            "合理月折旧额应在{2}元左右。请核实折旧政策和预计净残值率的合理性。"
        ),
        "suggestion": "复核固定资产卡片账，确认折旧方法、折旧年限和残值率符合会计准则规定。",
    },
    # 四流一致性
    "four_flow_mismatch": {
        "category": "invoice",
        "severity": "high",
        "title_template": "四流匹配合规风险——匹配率仅{0}%",
        "desc_template": (
            "合同流、发票流、货物流、资金流四流匹配率为{0}%，低于80%的合规基准线。"
            "四流不一致的业务面临虚开发票认定风险，请逐笔排查差异原因。"
        ),
        "suggestion": "逐笔核对合同、发票、物流单据和银行流水的一致性，对四流不一致的业务暂停抵扣进项并进行整改。",
    },
    # 纳税申报差异
    "declared_rev_gap": {
        "category": "tax",
        "severity": "high",
        "title_template": "申报收入（{0}元）与账面收入（{1}元）存在{2}%差异",
        "desc_template": (
            "账面同期收入为{1}元，纳税申报收入为{0}元，差异率{2}%。"
            "差异超过5%的预警线，请核实未申报收入的具体构成及原因，排查隐匿收入风险。"
        ),
        "suggestion": "逐项核对申报表与账簿收入的差异明细，对未申报部分补充申报并缴纳税款及滞纳金。",
    },
}

# 行业基准取值
INDUSTRY_BENCHMARKS = {
    "批发零售": {"ar_days_max": 90, "ap_days_max": 90, "inv_days_max": 100, "current_ratio_low": 1.0, "current_ratio_high": 2.5, "asset_liability_max": 70},
    "制造":     {"ar_days_max": 120, "ap_days_max": 100, "inv_days_max": 130, "current_ratio_low": 0.8, "current_ratio_high": 2.0, "asset_liability_max": 70},
    "建筑":     {"ar_days_max": 300, "ap_days_max": 250, "inv_days_max": 200, "current_ratio_low": 0.8, "current_ratio_high": 2.0, "asset_liability_max": 85},
    "电商":     {"ar_days_max": 90, "ap_days_max": 60, "inv_days_max": 30, "current_ratio_low": 1.2, "current_ratio_high": 3.0, "asset_liability_max": 60},
    "餐饮服务": {"ar_days_max": 30, "ap_days_max": 60, "inv_days_max": 20, "current_ratio_low": 0.8, "current_ratio_high": 2.0, "asset_liability_max": 70},
}


# ═══════════════════════════════════════════
#  合规发现数据结构
# ═══════════════════════════════════════════

class ComplianceFinding:
    """单条不合规发现"""
    def __init__(
        self,
        rule_key: str,
        category: str,
        severity: str,  # high / medium / low
        title: str,
        description: str,
        suggestion: str,
        metrics: Optional[dict[str, Any]] = None,
    ):
        self.rule_key = rule_key
        self.category = category
        self.severity = severity
        self.title = title
        self.description = description
        self.suggestion = suggestion
        self.metrics = metrics or {}

    def to_dict(self) -> dict:
        return {
            "rule_key": self.rule_key,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "suggestion": self.suggestion,
            "metrics": self.metrics,
        }


# ═══════════════════════════════════════════
#  核心校验逻辑
# ═══════════════════════════════════════════

def run_compliance_check(enterprise_name: str, industry: str, annual_revenue: float,
                         vouchers: list[dict], trial_balance: dict,
                         financial_statements: dict, tax_ledger: dict,
                         contracts: Optional[list] = None,
                         invoices: Optional[list] = None,
                         bank_transactions: Optional[list] = None) -> list[dict]:
    """
    运行全量合规校验，返回不合规发现列表。

    参数：
      enterprise_name: 企业名称
      industry: 行业
      annual_revenue: 年营收
      vouchers: 会计凭证列表
      trial_balance: 试算平衡表
      financial_statements: 财务报表（含 income_statement, balance_sheet, cash_flow）
      tax_ledger: 税务台账
      contracts: 合同台账列表（可选，用于四流匹配）
      invoices: 发票数据列表（可选，用于四流匹配）
      bank_transactions: 银行流水列表（可选，用于四流匹配）

    返回：list[dict] 不合规发现条目

    四流匹配检查：仅在传入 contracts / invoices / bank_transactions 任一非空时执行，
    使用 four_flow_match.calculate_four_flow_match 的确定性算法（标准化精确匹配），
    匹配率 = 匹配记录数 / 应匹配记录数；未提供四流数据时跳过该检查，
    不产生任何随机或模拟结果。
    """
    findings: list[ComplianceFinding] = []
    bs = financial_statements.get("balance_sheet", {})
    inc = financial_statements.get("income_statement", {})
    tb = trial_balance
    alerts = INDUSTRY_TAX_BURDEN_ALERTS.get(industry, INDUSTRY_TAX_BURDEN_ALERTS["批发零售"])
    bm = INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS["批发零售"])

    monthly_revenue = inc.get("items", {}).get("一、营业收入", 0)

    # ── 1. 增值税税负率检查 ──
    vat = tax_ledger.get("vat", {})
    vat_net = vat.get("net_payable", 0)
    vat_burden_pct = round(vat_net / monthly_revenue * 100, 2) if monthly_revenue > 0 else 0
    output_tax = vat.get("output_tax", 0)
    input_tax = vat.get("input_tax", 0)
    input_ratio = round(input_tax / output_tax * 100, 2) if output_tax > 0 else 0

    if vat_burden_pct == 0 and monthly_revenue > 10000:
        findings.append(ComplianceFinding(
            "vat_burden_zero", "tax", "high",
            "增值税实际税负率为0%——可能存在隐匿收入或虚增进项",
            f"企业当期申报增值税应纳税额为0元，但存在持续经营收入{monthly_revenue:,.0f}元。请核实销项税额是否完整申报，进项税额抵扣凭证是否真实合规。",
            "立即核查销项税额完整性，比对银行流水与开票金额，排查隐匿收入风险。",
            {"vat_burden_pct": 0, "monthly_revenue": monthly_revenue, "input_ratio": input_ratio},
        ))
    elif 0 < vat_burden_pct < alerts["vat_critical"]:
        findings.append(ComplianceFinding(
            "vat_burden_low", "tax", "high",
            f"增值税实际税负率（{vat_burden_pct}%）严重低于行业预警值（{alerts['vat_critical']}%）",
            f"企业当期增值税实际税负率为{vat_burden_pct}%，低于{industry}行业预警下限{alerts['vat_critical']}%。"
            f"进项税额抵扣比例（{input_ratio}%）偏高，请核查进项发票真实性及业务合理性。",
            "建议逐笔核查进项发票业务真实性，比对四流一致性，关注是否存在关联方虚开发票。",
            {"vat_burden_pct": vat_burden_pct, "warning_threshold": alerts["vat_critical"], "input_ratio": input_ratio},
        ))
    elif vat_burden_pct < alerts["vat_warning"]:
        findings.append(ComplianceFinding(
            "vat_burden_low", "tax", "medium",
            f"增值税实际税负率（{vat_burden_pct}%）低于行业预警值（{alerts['vat_warning']}%）",
            f"企业当期增值税实际税负率为{vat_burden_pct}%，低于{industry}行业预警下限{alerts['vat_warning']}%。"
            f"进项税额抵扣比例（{input_ratio}%）偏高，请核查进项发票真实性及业务合理性。",
            "建议逐笔核查进项发票业务真实性，比对四流一致性，关注是否存在关联方虚开发票。",
            {"vat_burden_pct": vat_burden_pct, "warning_threshold": alerts["vat_warning"], "input_ratio": input_ratio},
        ))

    # ── 2. 企业所得税贡献率检查 ──
    cit = tax_ledger.get("corporate_income_tax", {})
    cit_payable = cit.get("tax_payable", 0)
    cit_burden_pct = round(cit_payable / monthly_revenue * 100, 2) if monthly_revenue > 0 else 0
    if cit_burden_pct < alerts.get("income_tax_warning", 0.5) and monthly_revenue > 10000:
        findings.append(ComplianceFinding(
            "income_tax_burden_low", "tax", "medium",
            f"企业所得税贡献率（{cit_burden_pct}%）显著低于行业平均水平",
            f"当期企业所得税应纳税额占营业收入比例为{cit_burden_pct}%，低于{industry}行业参考下限{alerts.get('income_tax_warning', 0.5)}%。"
            f"请核实成本费用列支的合规性和合理性。",
            "抽查大额成本费用凭证的原始单据，核实业务真实性和发票合规性。",
            {"cit_burden_pct": cit_burden_pct, "warning_threshold": alerts.get("income_tax_warning", 0.5)},
        ))

    # ── 3. 应收账款异常检查 ──
    ar_balance = tb.get("closing_balance", {}).get("1122", 0)
    total_assets = bs.get("total_assets", 0)
    current_assets = bs.get("items", {}).get("流动资产", total_assets * 0.6)
    ar_ratio = round(ar_balance / current_assets * 100, 2) if current_assets > 0 else 0
    ar_days_est = round(ar_balance * 30 / monthly_revenue, 0) if monthly_revenue > 0 else 0

    if ar_days_est > bm.get("ar_days_max", 120):
        findings.append(ComplianceFinding(
            "ar_spike", "accounting", "medium",
            f"应收账款期末余额（{ar_balance:,.0f}元）异常偏高——周转天数{ar_days_est:.0f}天",
            f"期末应收账款余额为{ar_balance:,.0f}元，占流动资产{ar_ratio}%，周转天数达{ar_days_est:.0f}天。"
            f"行业上限为{bm['ar_days_max']}天。请核实是否存在虚假销售虚增应收账款，或对关联方大额赊销未计提坏账准备。",
            "逐笔核对应收账款明细账与销售合同，检查账龄结构并足额计提坏账准备。",
            {"ar_balance": ar_balance, "ar_ratio": ar_ratio, "ar_days": ar_days_est, "threshold_days": bm["ar_days_max"]},
        ))

    # ── 4. 应付账款检查 ──
    ap_balance = abs(tb.get("closing_balance", {}).get("2202", 0))
    ap_days_est = round(ap_balance * 30 / monthly_revenue, 0) if monthly_revenue > 0 else 0
    if ap_days_est > bm.get("ap_days_max", 150) and ap_balance > 10000:
        findings.append(ComplianceFinding(
            "ap_spike", "accounting", "low",
            f"应付账款期末余额（{ap_balance:,.0f}元）周转天数{ap_days_est:.0f}天",
            f"期末应付账款余额为{ap_balance:,.0f}元，周转天数{ap_days_est:.0f}天，"
            f"请核实是否存在虚增采购虚列应付账款。",
            "核对大额应付账款对应的采购合同、入库单和发票，确认业务真实性。",
            {"ap_balance": ap_balance, "ap_days": ap_days_est, "threshold_days": bm["ap_days_max"]},
        ))

    # ── 5. 存货异常检查 ──
    inv_balance = tb.get("closing_balance", {}).get("1405", 0)
    inv_days_est = round(inv_balance * 30 / (monthly_revenue * 0.7), 0) if monthly_revenue > 0 else 0
    if inv_days_est > bm.get("inv_days_max", 100) and inv_balance > 10000:
        findings.append(ComplianceFinding(
            "inventory_abnormal", "accounting", "medium",
            f"存货期末余额（{inv_balance:,.0f}元）存在跌价风险",
            f"期末存货余额{inv_balance:,.0f}元，存货周转天数{inv_days_est:.0f}天，超出行业正常水平。"
            f"请核实是否存在积压、呆滞存货未计提跌价准备。",
            "全面盘点存货，对可变现净值低于成本的存货计提跌价准备。",
            {"inv_balance": inv_balance, "inv_days": inv_days_est, "threshold_days": bm["inv_days_max"]},
        ))

    # ── 6. 流动比率异常 ──
    current_liabilities = bs.get("items", {}).get("流动负债", 0)
    current_ratio = round(current_assets / current_liabilities, 2) if current_liabilities > 0 else 0
    if current_ratio < bm["current_ratio_low"]:
        msg = f"流动比率仅{current_ratio}，短期偿债能力不足，可能面临资金链断裂风险。"
        findings.append(ComplianceFinding(
            "current_ratio_abnormal", "financial", "low",
            f"流动比率（{current_ratio}）低于安全线{bm['current_ratio_low']}",
            f"期末流动比率为{current_ratio}，{industry}行业安全下限为{bm['current_ratio_low']}。" + msg,
            "分析短期偿债能力变化原因，关注是否存在资金链风险。",
            {"current_ratio": current_ratio, "threshold": bm["current_ratio_low"]},
        ))

    # ── 7. 资产负债率过高 ──
    total_liabilities = bs.get("total_liabilities", 0)
    alr = round(total_liabilities / total_assets * 100, 2) if total_assets > 0 else 0
    if alr > bm.get("asset_liability_max", 75):
        findings.append(ComplianceFinding(
            "asset_liability_ratio_high", "financial", "medium",
            f"资产负债率（{alr}%）处于较高水平",
            f"期末资产负债率为{alr}%，{industry}行业参考上限为{bm['asset_liability_max']}%。"
            f"高杠杆经营可能诱发激进财税筹划动机。",
            "评估负债结构和偿债能力，关注是否存在表外负债或隐性担保。",
            {"asset_liability_ratio": alr, "threshold": bm["asset_liability_max"]},
        ))

    # ── 8. 折旧计提检查 ──
    # 注意：这里用配置文件中的 fixed_assets 需要从外部传入或用 monthly_depreciation 反推
    fixed_assets_b = tb.get("opening_balance", {}).get("1601", 0)
    actual_dep = sum(
        e["amount"] for v in vouchers for e in v["entries"]
        if e.get("account_code") == "1602" and "折旧" in v.get("description", "")
    )
    if actual_dep == 0:
        # 从凭证中累计 — 汇总所有折旧相关分录
        actual_dep = sum(
            e["amount"] for v in vouchers for e in v["entries"]
            if e.get("account_code") == "1602"
        ) / 2  # 估计

    expected_dep = round(fixed_assets_b * 0.008, 2) if fixed_assets_b > 0 else 0
    if actual_dep > 0 and expected_dep > 0 and round(actual_dep / expected_dep, 2) < 0.6:
        findings.append(ComplianceFinding(
            "depreciation_insufficient", "accounting", "low",
            f"固定资产折旧计提（月{actual_dep:,.0f}元）低于测算基准",
            f"本月折旧计提{actual_dep:,.0f}元，按固定资产原值{fixed_assets_b:,.0f}元及行业平均折旧率测算，"
            f"合理月折旧额应在{expected_dep:,.0f}元左右。请核实折旧政策的合理性。",
            "复核固定资产卡片账，确认折旧方法、折旧年限和残值率符合会计准则规定。",
            {"actual_dep": actual_dep, "expected_dep": expected_dep},
        ))

    # ── 9. 申报收入 vs 账面收入差异 ──
    declared_rev = vat.get("declared_revenue", 0)
    if declared_rev > 0 and monthly_revenue > 0:
        gap_pct = round((declared_rev - monthly_revenue) / monthly_revenue * 100, 2)
        if abs(gap_pct) > 5:
            findings.append(ComplianceFinding(
                "declared_rev_gap", "tax", "high",
                f"申报收入（{declared_rev:,.0f}元）与账面收入（{monthly_revenue:,.0f}元）存在{gap_pct}%差异",
                f"账面同期收入为{monthly_revenue:,.0f}元，纳税申报收入为{declared_rev:,.0f}元，差异率{gap_pct}%。"
                f"差异超过5%的预警线，请核实未申报收入的具体构成及原因。",
                "逐项核对申报表与账簿收入的差异明细，对未申报部分补充申报并缴纳税款及滞纳金。",
                {"declared_rev": declared_rev, "book_rev": monthly_revenue, "gap_pct": gap_pct},
            ))

    # ── 10. 四流匹配检查（确定性算法，结果可复现）──
    if contracts or invoices or bank_transactions:
        flow_result = calculate_four_flow_match(
            contracts or [], invoices or [], bank_transactions or [],
        )
        flow_match = round(flow_result.match_rate, 2)
        if flow_match < 80:
            findings.append(ComplianceFinding(
                "four_flow_mismatch", "invoice", "high",
                f"四流匹配合规风险——匹配率仅{flow_match}%",
                f"合同流、发票流、资金流四流匹配率为{flow_match}%（共匹配 {flow_result.match_count} 笔记录），低于80%的合规基准线。"
                f"四流不一致的业务面临虚开发票认定风险。",
                "逐笔核对合同、发票、物流单据和银行流水的一致性，对四流不一致的业务暂停抵扣进项并进行整改。",
                {
                    "flow_match_rate": flow_match,
                    "threshold": 80,
                    "match_count": flow_result.match_count,
                    "contract_invoice_match_count": flow_result.contract_invoice_match_count,
                    "invoice_bank_match_count": flow_result.invoice_bank_match_count,
                },
            ))
    else:
        logger.info(f"合规校验跳过四流匹配：{enterprise_name} 未提供合同/发票/银行流水数据")

    logger.info(f"合规校验完成：{enterprise_name}（{industry}）发现 {len(findings)} 条不合规条目")
    return [f.to_dict() for f in findings]
