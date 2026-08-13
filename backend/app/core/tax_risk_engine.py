"""
五维全景税务风险评估引擎 (tax_risk_engine.py)

基于金税四期"三流一致→四流匹配→五维穿透"的递进式稽查逻辑，
对企业的财税合规风险进行五维全景评估。

五维体系：
  维度一【异质性宏观内控】 — 行业基准对标，重/轻资产差异化审查
  维度二【增值税 GAAR 反避税】 — 一般反避税规则，四流偏离度
  维度三【个税隐性分红穿透】 — 股东借款超365天强制还原股息红利
  维度四【复合惩罚敞口推演】 — 调用 penalty_calculator 进行毁灭性罚款推演
  维度五【四流匹配风险量化】 — 沿用现有 risk_engine 7维评分

技术红线：
  - 所有金额/比率运算强制使用 decimal.Decimal
  - 所有风险预警输出双语（商业语言 + 财务技术语言）
  - 严禁调用大模型 API 进行任何文本推演
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.penalty_calculator import (
    UnpaidTaxInput,
    CompoundPenaltyResult,
    calculate_compound_penalty_exposure,
    _calculate_iit_hidden_dividend,
    IIT_DIVIDEND_RATE,
    PENALTY_MULTIPLIER,
    GHOST_INVOICE_MULTIPLIER,
)


# ═══════════════════════════════════════════════════════
# 枚举与异常
# ═══════════════════════════════════════════════════════

class InternalControlFailureWarning(Exception):
    """
    内控系统性崩溃异常。

    当成本费用率超过行业基准 1.5 倍以上，或四流匹配度
    连续 3 期低于 40%（即 is_internal_control_failed=True）
    时抛出，阻断后续评估流程。
    """
    def __init__(self, enterprise_name: str, reason: str, detail: str):
        self.enterprise_name = enterprise_name
        self.reason = reason
        self.detail = detail
        super().__init__(f"[{enterprise_name}] 内控崩溃: {reason}")


class GAARViolationWarning(Exception):
    """
    增值税 GAAR 反避税违规异常。

    当发现缺乏合理商业目的的避税安排时抛出，
    包括转让定价畸低、资金闭环回流等情形。
    """
    def __init__(self, enterprise_name: str, violation_type: str, detail: str):
        self.enterprise_name = enterprise_name
        self.violation_type = violation_type
        self.detail = detail
        super().__init__(f"[{enterprise_name}] GAAR违规: {violation_type}")


class AssessmentDimension(StrEnum):
    """评估维度枚举"""
    MACRO_INTERNAL_CONTROL = "macro_internal_control"   # 异质性宏观内控
    VAT_GAAR = "vat_gaar"                               # 增值税GAAR
    IIT_HIDDEN_DIVIDEND = "iit_hidden_dividend"         # 个税隐性分红穿透
    COMPOUND_PENALTY = "compound_penalty"               # 复合惩罚敞口
    FOUR_FLOW_MATCH = "four_flow_match"                 # 四流匹配


# ═══════════════════════════════════════════════════════
# 各维度法规依据（policy_ref 条文索引 / policy_basis 条文说明）
# ═══════════════════════════════════════════════════════

POLICY_REFERENCES: dict[str, dict[str, str]] = {
    "macro_internal_control": {
        "policy_ref": "《中华人民共和国税收征收管理法》第十九条、《中华人民共和国企业所得税法》第八条",
        "risk_reason": "账簿与凭证管理不合规，成本费用列支缺少合法有效凭证支撑",
        "policy_basis": (
            "《税收征收管理法》第十九条：纳税人、扣缴义务人应当按照规定设置账簿，根据合法、有效凭证记账、核算。"
            "《企业所得税法》第八条：企业实际发生的与取得收入有关的、合理的支出，"
            "准予在计算应纳税所得额时扣除。"
        ),
    },
    "vat_gaar": {
        "policy_ref": "《中华人民共和国税收征收管理法》第三十五条、《中华人民共和国企业所得税法》第四十一条",
        "risk_reason": "交易定价或四流结构缺乏合理商业目的，涉嫌规避增值税纳税义务",
        "policy_basis": (
            "《税收征收管理法》第三十五条：纳税人申报的计税依据明显偏低，又无正当理由的，"
            "税务机关有权核定其应纳税额。"
            "《企业所得税法》第四十一条：企业与其关联方之间的业务往来，不符合独立交易原则而减少企业"
            "或者其关联方应纳税收入或者所得额的，税务机关有权按照合理方法调整。"
        ),
    },
    "iit_hidden_dividend": {
        "policy_ref": "《财政部 国家税务总局关于规范个人投资者个人所得税征收管理的通知》（财税〔2003〕158号）第二条",
        "risk_reason": "股东借款纳税年度终了未归还且未用于生产经营，被视同股息红利分配",
        "policy_basis": (
            "纳税年度内个人投资者从其投资的企业借款，在该纳税年度终了后既不归还，又未用于企业生产经营的，"
            "其未归还的借款可视为企业对个人投资者的红利分配，依照\"利息、股息、红利所得\"项目计征个人所得税。"
        ),
    },
    "compound_penalty": {
        "policy_ref": "《中华人民共和国税收征收管理法》第三十二条、第六十三条",
        "risk_reason": "存在欠缴税款、隐匿收入或虚开发票等情形，面临补税+滞纳金+罚款的复合敞口",
        "policy_basis": (
            "《税收征收管理法》第三十二条：纳税人未按照规定期限缴纳税款的，从滞纳税款之日起，"
            "按日加收滞纳税款万分之五的滞纳金。"
            "第六十三条：对纳税人偷税的，由税务机关追缴其不缴或者少缴的税款、滞纳金，"
            "并处不缴或者少缴的税款百分之五十以上五倍以下的罚款。"
        ),
    },
    "four_flow_match": {
        "policy_ref": "《国家税务总局关于加强增值税征收管理若干问题的通知》（国税发〔1995〕192号）第一条第（三）项",
        "risk_reason": "合同、发票、资金、货物流之间存在不一致，进项税额抵扣可能不被认可",
        "policy_basis": (
            "纳税人购进货物或应税劳务、支付运输费用，所支付款项的单位，必须与开具抵扣凭证的销货单位、"
            "提供劳务的单位一致，方可申报抵扣进项税额。四流不一致将导致进项税额抵扣被否认，"
            "并可能被认定为虚开发票。"
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


# ═══════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════

@dataclass
class ComprehensiveTaxRiskResult:
    """五维全景税务风险评估结果"""

    # ── 企业标识 ──
    enterprise_id: str = ""
    enterprise_name: str = ""
    assessment_date: str = ""

    # ── 总体风险 ──
    overall_risk_level: str = "low"                    # critical/high/medium/low
    overall_risk_score: float = 0.0                    # 0-100

    # ── 五维分项得分 ──
    dimension_scores: dict[str, float] = field(default_factory=dict)

    # ── 各维度详情（双语） ──
    dim_details: dict[str, dict] = field(default_factory=dict)

    # ── 风险标记 ──
    risk_flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # ── 内控状态 ──
    is_internal_control_failed: bool = False
    internal_control_reason: str = ""

    # ── GAAR 违规 ──
    gaar_violations: list[dict] = field(default_factory=list)

    # ── 个税穿透 ──
    iit_hidden_dividend_amount: Decimal = Decimal("0")
    iit_penetration_detail: str = ""

    # ── 惩罚敞口 ──
    compound_penalty: CompoundPenaltyResult | None = None

    # ── 双语输出 ──
    business_narrative: str = ""
    technical_summary: dict[str, Any] = field(default_factory=dict)

    # ── 元数据 ──
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnterpriseDataPayload:
    """
    企业综合数据载荷。

    将分散在 enterprises / bank_transactions / invoices /
    contracts / tax_declarations / financial_statements 等
    表中的数据聚合为一个统一输入结构，供引擎消费。
    """
    enterprise_id: str = ""
    enterprise_name: str = ""
    industry: str = ""                                 # 行业类型
    industry_benchmark_id: str | None = None

    # ── 财务指标 ──
    revenue_annual: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")             # 期间费用合计
    net_profit: Decimal = Decimal("0")
    total_assets: Decimal = Decimal("0")

    # ── 资产特征 ──
    asset_type: str = "light_asset"                   # heavy_asset / light_asset
    depreciation_amount: Decimal = Decimal("0")       # 固定资产折旧额
    intangible_amortization: Decimal = Decimal("0")   # 无形资产摊销额
    service_fee_total: Decimal = Decimal("0")         # 劳务/服务费总额（关注费用化冲账）

    # ── 税收数据 ──
    declared_tax: Decimal = Decimal("0")              # 申报税额
    actual_paid: Decimal = Decimal("0")               # 实际缴纳
    input_invoice_total: Decimal = Decimal("0")       # 进项税额
    output_invoice_total: Decimal = Decimal("0")      # 销项税额

    # ── 四流数据 ──
    bank_transactions: list[dict] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)
    contracts: list[dict] = field(default_factory=list)

    # ── 其他应收款明细（个税穿透用） ──
    other_receivables: list[dict] = field(
        default_factory=list,
        # 每项：{"borrower": str, "amount": Decimal, "loan_date": date, "relation": str}
    )

    # ── 行业基准 ──
    std_tax_burden_rate: Decimal = Decimal("0")
    max_cost_expense_ratio: Decimal = Decimal("0")
    depreciation_to_revenue_ratio: Decimal = Decimal("0")

    # ── 企业属性 ──
    is_high_tech: bool = False
    is_small_micro: bool = False
    is_internal_control_failed: bool = False

    # ── 风险历史 ──
    previous_risk_level: str = "low"
    consecutive_high_risk_periods: int = 0


# ═══════════════════════════════════════════════════════
# 维度一：异质性宏观内控审查
# ═══════════════════════════════════════════════════════

def _assess_macro_internal_control(
    payload: EnterpriseDataPayload,
) -> tuple[float, list[str], list[str], dict]:
    """
    维度一：异质性宏观内控审查。

    根据企业资产类型（heavy_asset / light_asset）执行差异化
    审查策略，并检测成本费用率是否超过行业基准 1.5 倍阈值。

    规则对应条款：
      ─ 重资产（heavy_asset）：审查固定资产折旧在总成本中的
        占比，若超过 depreciation_to_revenue_ratio，标记为
        违规资本化异常。
      ─ 轻资产（light_asset）：紧盯无形资产摊销及巨额服务费，
        若无形劳务费用激增，锁定"费用化冲账"嫌疑。
      ─ 通用：成本费用率 = (总成本 + 各项费用) / 营业收入，
        若大于行业 max_cost_expense_ratio 的 1.5 倍，立即
        阻断流程并抛出 InternalControlFailureWarning。

    Returns:
        (风险分, 风险标记, 整改建议, 技术详情dict)
    """
    flags: list[str] = []
    recs: list[str] = []
    tech_detail: dict[str, Any] = {
        "asset_type": payload.asset_type,
        "depreciation_check": {},
        "intangible_amortization_check": {},
        "cost_expense_ratio_check": {},
    }

    # ── 1a. 重资产：折旧占比审查 ──
    if payload.asset_type == "heavy_asset":
        if payload.revenue_annual > Decimal("0") and payload.depreciation_amount > Decimal("0"):
            # 折旧/营收比 = depreciation / revenue
            dep_ratio = (
                payload.depreciation_amount / payload.revenue_annual
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

            threshold = payload.depreciation_to_revenue_ratio
            tech_detail["depreciation_check"] = {
                "depreciation": str(payload.depreciation_amount),
                "revenue": str(payload.revenue_annual),
                "dep_ratio": str(dep_ratio),
                "threshold": str(threshold),
            }

            if threshold > Decimal("0") and dep_ratio > threshold:
                flags.append(
                    f"重资产企业折旧营收比 {dep_ratio:.4f} > 警戒线 {threshold:.4f}，"
                    f"存在违规资本化异常——固定资产折旧占比过高，可能通过延长折旧年限、"
                    f"减少当期费用来粉饰利润"
                )
                recs.append(
                    "核查固定资产折旧政策是否符合税法规定，"
                    "检查是否存在延迟计提折旧或资本化费用化的舞弊行为"
                )
                tech_detail["depreciation_check"]["violation"] = True
            else:
                tech_detail["depreciation_check"]["violation"] = False

    # ── 1b. 轻资产：无形摊销及服务费审查 ──
    elif payload.asset_type == "light_asset":
        susp_count = 0
        susp_details = []

        # 检查无形资产摊销异常
        if payload.intangible_amortization > Decimal("0") and payload.total_cost > Decimal("0"):
            intangible_ratio = (
                payload.intangible_amortization / payload.total_cost
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            tech_detail["intangible_amortization_check"] = {
                "amortization": str(payload.intangible_amortization),
                "total_cost": str(payload.total_cost),
                "ratio": str(intangible_ratio),
            }

            if intangible_ratio > Decimal("0.10"):  # 摊销占总成本>10% 异常
                susp_count += 1
                susp_details.append(
                    f"无形资产摊销占总成本 {float(intangible_ratio):.1%}，"
                    f"偏离正常水平，疑似通过无形资产摊销调节利润"
                )

        # 检查服务费激增（>营收30%视为异常）
        if payload.service_fee_total > Decimal("0") and payload.revenue_annual > Decimal("0"):
            service_ratio = (
                payload.service_fee_total / payload.revenue_annual
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            tech_detail["service_fee_check"] = {
                "service_fee_total": str(payload.service_fee_total),
                "revenue": str(payload.revenue_annual),
                "ratio": str(service_ratio),
            }

            if service_ratio > Decimal("0.30"):
                susp_count += 1
                susp_details.append(
                    f"服务费/劳务费占营收 {float(service_ratio):.1%}，"
                    f"疑似通过大额劳务费进行'费用化冲账'——将本应资本化的支出"
                    f"通过关联公司开票转化为当期费用，虚增成本侵蚀税基"
                )

        if susp_count > 0:
            flags.extend(susp_details)
            recs.append(
                "审查大额服务费和无形资产摊销的合同实质，"
                "排查关联方交易定价是否公允、是否具有真实商业目的"
            )
            tech_detail["violation_count"] = susp_count

    # ── 1c. 通用：成本费用率审查 ──
    if payload.revenue_annual > Decimal("0"):
        # 成本费用率 = (总成本 + 各项费用) / 营业收入
        total_cost_expense = payload.total_cost + payload.total_expenses
        cost_expense_ratio = (
            total_cost_expense / payload.revenue_annual
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        benchmark = payload.max_cost_expense_ratio
        tech_detail["cost_expense_ratio_check"] = {
            "total_cost": str(payload.total_cost),
            "total_expenses": str(payload.total_expenses),
            "revenue": str(payload.revenue_annual),
            "actual_ratio": str(cost_expense_ratio),
            "industry_benchmark": str(benchmark),
            "threshold_1_5x": str(benchmark * Decimal("1.5")),
        }

        if benchmark > Decimal("0") and cost_expense_ratio > benchmark * Decimal("1.5"):
            # 触发内控崩溃阻断
            reason = (
                f"成本费用率 {float(cost_expense_ratio):.1%} > "
                f"行业基准 {float(benchmark):.1%} × 1.5 (= {float(benchmark * Decimal('1.5')):.1%})，"
                f"内控体系系统性崩溃"
            )
            detail = (
                f"[技术详情] actual_ratio={cost_expense_ratio}, "
                f"benchmark={benchmark}, "
                f"1.5x_threshold={benchmark * Decimal('1.5')}, "
                f"total_cost={payload.total_cost}, "
                f"total_expenses={payload.total_expenses}, "
                f"revenue={payload.revenue_annual}"
            )
            raise InternalControlFailureWarning(
                payload.enterprise_name, reason, detail
            )

    # ── 风险分计算 ──
    if not flags:
        return 0.0, [], [], tech_detail

    score = min(100.0, float(len(flags) * 25.0))
    return score, flags, recs, tech_detail


# ═══════════════════════════════════════════════════════
# 维度二：增值税 GAAR 反避税（一般反避税规则）
# ═══════════════════════════════════════════════════════

def _assess_vat_gaar(
    payload: EnterpriseDataPayload,
) -> tuple[float, list[str], list[str], list[dict]]:
    """
    维度二：增值税 GAAR 反避税审查。

    依据《中华人民共和国增值税法》及《税收征收管理法》第35条，
    对关联交易进行一般反避税规则（GAAR）审查。

    审查要点：
      ─ 遍历合同、发票、银行流水三方数据，比较金额偏离度
      ─ 若无形资产转让定价畸低（含税价 < 市价 30%）且资金在
        短时间内闭环回流（≤30天），直接判定为缺乏合理商业目的
        的避税安排，抛出 GAARViolationWarning
      ─ 报关、物流、资金与发票偏离度超标，列为反避税风险

    Returns:
        (风险分, 风险标记, 整改建议, GAAR违规详情列表)
    """
    flags: list[str] = []
    recs: list[str] = []
    violations: list[dict] = []

    # ── 2a. 逐笔交易四流偏离度比对 ──
    # 对每笔合同，查找对应的发票和银行流水
    for contract in payload.contracts:
        ct_amount = Decimal(str(contract.get("contract_amount", 0)))
        ct_no = contract.get("contract_no", "unknown")
        counterparty = contract.get("counterparty", "unknown")

        # 查找对应发票
        matched_invoices = [
            inv for inv in payload.invoices
            if inv.get("buyer_name") == counterparty or
               inv.get("seller_name") == counterparty
        ]
        inv_total = sum(
            (Decimal(str(inv.get("total_amount", 0)))
             for inv in matched_invoices),
            Decimal("0")
        )

        # 查找对应银行流水
        matched_txs = [
            tx for tx in payload.bank_transactions
            if tx.get("counterparty") == counterparty
        ]
        bank_total = sum(
            (Decimal(str(tx.get("amount", 0)))
             for tx in matched_txs),
            Decimal("0")
        )

        # ── 合同 vs 发票偏离 ──
        if ct_amount > Decimal("0"):
            invoice_dev = (
                (ct_amount - inv_total) / ct_amount
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        else:
            invoice_dev = Decimal("0")

        if abs(invoice_dev) > Decimal("0.30"):
            flags.append(
                f"合同 {ct_no} 金额 ¥{ct_amount:,.2f} 与发票总额 "
                f"¥{inv_total:,.2f} 偏离 {float(invoice_dev):.1%}，"
                f"存在拆分合同或虚开发票嫌疑"
            )

        # ── 资金闭环回流检测 ──
        # 条件：30天内同一对手方先 outflow 后 inflow，金额差<10%
        counterparty_txs = sorted(
            [tx for tx in payload.bank_transactions
             if tx.get("counterparty") == counterparty],
            key=lambda x: x.get("transaction_date", "2000-01-01")
        )
        if len(counterparty_txs) >= 2:
            try:
                first = counterparty_txs[0]
                last = counterparty_txs[-1]
                first_date = (
                    first.get("transaction_date")
                    if isinstance(first.get("transaction_date"), date)
                    else date.fromisoformat(str(first.get("transaction_date", "2000-01-01")))
                )
                last_date = (
                    last.get("transaction_date")
                    if isinstance(last.get("transaction_date"), date)
                    else date.fromisoformat(str(last.get("transaction_date", "2000-01-01")))
                )
                days_diff = (last_date - first_date).days

                first_amt = Decimal(str(first.get("amount", 0)))
                last_amt = Decimal(str(last.get("amount", 0)))

                if first_amt > Decimal("0"):
                    return_ratio = (
                        (last_amt - first_amt) / first_amt
                    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                else:
                    return_ratio = Decimal("0")

                if days_diff <= 30 and abs(return_ratio) < Decimal("0.10"):
                    violation = {
                        "type": "capital_loopback",
                        "counterparty": counterparty,
                        "contract_no": ct_no,
                        "first_amount": str(first_amt),
                        "last_amount": str(last_amt),
                        "days_diff": days_diff,
                        "return_ratio": str(return_ratio),
                    }
                    violations.append(violation)
                    msg = (
                        f"GAAR 预警：对手方 {counterparty} 在 {days_diff} 天内"
                        f"完成资金闭环回流（¥{first_amt:,.2f} → ¥{last_amt:,.2f}），"
                        f"回流偏差 {float(abs(return_ratio)):.1%}，缺乏合理商业目的，"
                        f"判定为避税安排"
                    )
                    flags.append(msg)
                    raise GAARViolationWarning(
                        payload.enterprise_name,
                        "capital_loopback",
                        msg,
                    )
            except GAARViolationWarning:
                raise  # 向上传播
            except Exception:
                pass  # 日期解析失败时跳过

        # ── 无形资产转让定价审查 ──
        product_name = contract.get("product_name", "")
        is_intangible = any(kw in str(product_name) for kw in
                          ["无形资产", "专利", "商标", "版权", "软件", "技术", "许可"])

        if is_intangible and ct_amount > Decimal("0") and inv_total > Decimal("0"):
            # 判断转让价格是否畸低（<30%市场价——此处用合同价 vs 发票价近似）
            price_ratio = (ct_amount / inv_total).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            if price_ratio < Decimal("0.30"):
                violation = {
                    "type": "transfer_pricing_abuse",
                    "product": product_name,
                    "contract_amount": str(ct_amount),
                    "invoice_amount": str(inv_total),
                    "price_ratio": str(price_ratio),
                }
                violations.append(violation)
                flags.append(
                    f"无形资产'{product_name}'转让定价畸低——合同价 ¥{ct_amount:,.2f} "
                    f"仅为开票价 ¥{inv_total:,.2f} 的 {float(price_ratio):.1%}，"
                    f"涉嫌通过关联交易转移利润规避增值税"
                )
                recs.append(
                    f"核查'{product_name}'的独立交易价格，"
                    "准备转让定价同期资料（国别报告/主体文档/本地文档）"
                )

    # ── 风险分计算 ──
    if not flags and not violations:
        return 0.0, [], [], []

    base_score = float(len(flags) * 20.0 + len(violations) * 15.0)
    score = min(100.0, base_score)
    return score, flags, recs, violations


# ═══════════════════════════════════════════════════════
# 维度三：个税隐性分红穿透
# ═══════════════════════════════════════════════════════

def _assess_iit_hidden_dividend(
    payload: EnterpriseDataPayload,
) -> tuple[float, list[str], list[str], Decimal, str]:
    """
    维度三：个税隐性分红穿透。

    依据：财税[2003]158号——股东从其投资企业借款，在纳税年度
    终了后既不归还又未用于企业生产经营的，未归还的借款可视为
    企业对个人投资者的红利分配，按"利息、股息、红利所得"项
    目计征 20% 个人所得税。

    筛选规则：
      ─ 从"其他应收款"明细中筛选股东及其直系亲属借款
      ─ 借款满 365 天未归还 → 触发穿透
      ─ unpaid_iit = 借款总额 × 20%

    Returns:
        (风险分, 风险标记, 整改建议, 个税穿透金额, 技术详情)
    """
    flags: list[str] = []
    recs: list[str] = []

    shareholder_loan_total = Decimal("0")
    triggered_items: list[dict] = []
    today = date.today()

    for item in payload.other_receivables:
        relation = item.get("relation", "")
        # 筛选股东及直系亲属
        is_shareholder = any(kw in str(relation) for kw in
                           ["股东", "法人", "董事长", "总经理", "直系亲属",
                            "配偶", "子女", "父母", "兄妹", "兄弟", "姐妹"])

        if not is_shareholder:
            continue

        loan_amount = Decimal(str(item.get("amount", 0)))
        loan_date_raw = item.get("loan_date")

        # 解析日期
        if isinstance(loan_date_raw, date):
            loan_date = loan_date_raw
        elif isinstance(loan_date_raw, str):
            try:
                loan_date = date.fromisoformat(loan_date_raw)
            except ValueError:
                continue
        else:
            continue

        days_overdue = (today - loan_date).days
        if days_overdue < 365:
            continue  # 未满365天，不触发穿透

        shareholder_loan_total += loan_amount
        triggered_items.append({
            "borrower": item.get("borrower", "unknown"),
            "relation": relation,
            "amount": str(loan_amount),
            "loan_date": str(loan_date),
            "days_overdue": days_overdue,
        })

    # 调用穿透计算
    if shareholder_loan_total > Decimal("0"):
        # 至少满365天才触发
        max_days = max((d["days_overdue"] for d in triggered_items),
                       default=0)
        unpaid_iit = _calculate_iit_hidden_dividend(
            shareholder_loan_total, max_days
        )

        borrowers = ", ".join(
            f"{d['borrower']}({d['relation']}, {d['days_overdue']}天)"
            for d in triggered_items[:5]
        )
        flags.append(
            f"股东及其直系亲属借款超365天未归还共计 "
            f"¥{shareholder_loan_total:,.2f}（{len(triggered_items)}笔），"
            f"按财税[2003]158号穿透还原为股息红利，应补缴个税 "
            f"¥{unpaid_iit:,.2f}（20%税率）"
        )
        recs.append(
            "立即通知股东归还借款或准备分红决议，"
            "补代扣代缴个人所得税，避免滞纳金和罚款"
        )

        tech_detail = (
            f"shareholder_loan_total={shareholder_loan_total}, "
            f"triggered_items={len(triggered_items)}, "
            f"iit_rate={IIT_DIVIDEND_RATE}, "
            f"unpaid_iit={unpaid_iit}"
        )
    else:
        unpaid_iit = Decimal("0")
        tech_detail = "no_shareholder_loans_triggered"

    if not flags:
        return 0.0, [], [], Decimal("0"), tech_detail

    score = min(100.0, float(unpaid_iit / Decimal("10000") * 10))
    return score, flags, recs, unpaid_iit, tech_detail


# ═══════════════════════════════════════════════════════
# 五维全景评估主入口
# ═══════════════════════════════════════════════════════

async def calculate_comprehensive_tax_risk(
    enterprise_id: str,
    payload: EnterpriseDataPayload,
    db_session: AsyncSession,
) -> ComprehensiveTaxRiskResult:
    """
    五维全景税务风险评估主入口。

    依次执行：
      1. 异质性宏观内控审查（阻塞点：内控崩溃异常）
      2. 增值税 GAAR 反避税审查（阻塞点：GAAR违规异常）
      3. 个税隐性分红穿透
      4. 复合惩罚敞口推演
      5. 四流匹配风险量化

    Args:
        enterprise_id: 企业ID
        payload: 企业数据载荷（聚合了所有相关表的业务数据）
        db_session: 异步数据库会话（用于加载 IndustryBenchmark 等关联数据）

    Returns:
        ComprehensiveTaxRiskResult: 结构化五维全景评估结果

    Raises:
        InternalControlFailureWarning: 内控体系系统性崩溃
        GAARViolationWarning: 一般反避税规则违规
    """
    from datetime import timezone as tz

    result = ComprehensiveTaxRiskResult(
        enterprise_id=enterprise_id,
        enterprise_name=payload.enterprise_name,
        assessment_date=datetime.now(tz.utc).isoformat(),
    )

    dim_scores: dict[str, float] = {}
    dim_details: dict[str, dict] = {}

    # ═══════════════════════════════════════════════════
    # 维度一：异质性宏观内控审查
    # ═══════════════════════════════════════════════════
    try:
        score_1, flags_1, recs_1, tech_1 = _assess_macro_internal_control(payload)
    except InternalControlFailureWarning as e:
        # 内控崩溃 → 立即写回 Enterprise 表并终止评估
        from sqlalchemy import update
        from app.models.enterprise import Enterprise, RiskLevelEnhanced

        await db_session.execute(
            update(Enterprise)
            .where(Enterprise.id == enterprise_id)
            .values(is_internal_control_failed=True, risk_level=RiskLevelEnhanced.CRITICAL)
        )
        await db_session.commit()

        result.is_internal_control_failed = True
        result.internal_control_reason = e.reason
        result.overall_risk_level = "critical"
        result.overall_risk_score = 100.0
        result.business_narrative = (
            f"「{payload.enterprise_name}」内控体系系统性崩溃！\n"
            f"原因：{e.reason}\n"
            f"技术详情：{e.detail}\n\n"
            f"建议：立即暂停高风险交易，委托税务师进行全面自查，"
            f"重点审查成本费用列支的真实性和合规性。"
        )
        result.technical_summary = {
            "status": "internal_control_failed",
            "reason": e.reason,
            "detail": e.detail,
        }
        result.dimension_scores = {"macro_internal_control": 100.0}
        result.dim_details = {
            "macro_internal_control": _with_policy_basis(
                "macro_internal_control",
                {"score": 100.0, "detail": e.reason},
                [e.reason],
            )
        }
        result.risk_flags = [e.reason]
        result.recommendations = ["立即停止高风险操作，聘请注册税务师进行企业全面自查"]
        return result

    dim_scores["macro_internal_control"] = score_1
    dim_details["macro_internal_control"] = _with_policy_basis(
        "macro_internal_control",
        {
            "score": score_1,
            "detail": f"资产类型: {payload.asset_type}，成本费用率与行业基准比对",
            "technical_detail": tech_1,
        },
        flags_1,
    )
    result.risk_flags.extend(flags_1)
    result.recommendations.extend(recs_1)

    # ═══════════════════════════════════════════════════
    # 维度二：增值税 GAAR 反避税
    # ═══════════════════════════════════════════════════
    try:
        score_2, flags_2, recs_2, gaar_violations = _assess_vat_gaar(payload)
    except GAARViolationWarning as e:
        # GAAR 违规 → 记录并继续（不阻断整体评估，但标记为严重）
        score_2 = 100.0
        flags_2 = [f"GAAR 违规: {e.violation_type} — {e.detail}"]
        recs_2 = ["立即暂停关联交易，准备转让定价同期资料，必要时申请预约定价安排(APA)"]
        gaar_violations = [{"type": e.violation_type, "detail": e.detail}]

    dim_scores["vat_gaar"] = score_2
    dim_details["vat_gaar"] = _with_policy_basis(
        "vat_gaar",
        {
            "score": score_2,
            "detail": "增值税一般反避税规则审查——四流偏离度与转让定价",
            "technical_detail": {"violations_count": len(gaar_violations), "violations": gaar_violations},
        },
        flags_2,
    )
    result.risk_flags.extend(flags_2)
    result.recommendations.extend(recs_2)
    result.gaar_violations = gaar_violations

    # ═══════════════════════════════════════════════════
    # 维度三：个税隐性分红穿透
    # ═══════════════════════════════════════════════════
    score_3, flags_3, recs_3, iit_amount, iit_detail = _assess_iit_hidden_dividend(payload)

    dim_scores["iit_hidden_dividend"] = score_3
    dim_details["iit_hidden_dividend"] = _with_policy_basis(
        "iit_hidden_dividend",
        {
            "score": score_3,
            "detail": f"股东借款穿透还原——应补个税 ¥{iit_amount:,.2f}",
            "technical_detail": iit_detail,
        },
        flags_3,
    )
    result.risk_flags.extend(flags_3)
    result.recommendations.extend(recs_3)
    result.iit_hidden_dividend_amount = iit_amount
    result.iit_penetration_detail = iit_detail

    # ═══════════════════════════════════════════════════
    # 维度四：复合惩罚敞口推演
    # ═══════════════════════════════════════════════════
    # 根据前三维度得分推算风险等级（用于罚款倍数选择）
    avg_risk = sum(dim_scores.values()) / max(len(dim_scores), 1)
    if avg_risk >= 70:
        penalty_risk_level = "high"
    elif avg_risk >= 40:
        penalty_risk_level = "medium"
    else:
        penalty_risk_level = "low"

    # 计算欠税估算
    unpaid_vat = (payload.output_invoice_total - payload.input_invoice_total).max(
        Decimal("0")
    )
    # 企业所得税简化估算
    tax_gap = payload.declared_tax - payload.actual_paid
    unpaid_cit = tax_gap.max(Decimal("0")) if tax_gap > Decimal("0") else Decimal("0")

    # 滞纳天数预测（假设从最近一次申报期算起 180 天）
    estimated_late_days = 180

    penalty_input = UnpaidTaxInput(
        unpaid_vat=unpaid_vat,
        unpaid_cit=unpaid_cit,
        unpaid_iit=iit_amount,
        unpaid_other=Decimal("0"),
        late_days=estimated_late_days,
        risk_level=penalty_risk_level,
        has_ghost_invoice=(len(gaar_violations) > 0),
    )

    penalty_result = calculate_compound_penalty_exposure(penalty_input)
    result.compound_penalty = penalty_result

    dim_scores["compound_penalty"] = min(
        100.0,
        float(penalty_result.total_exposure / (payload.revenue_annual + Decimal("1")) * 100),
    )
    dim_details["compound_penalty"] = _with_policy_basis(
        "compound_penalty",
        {
            "score": dim_scores["compound_penalty"],
            "detail": (
                f"预计总敞口 ¥{penalty_result.total_exposure:,.2f} "
                f"（本金+罚款+滞纳金{f'+虚开' if penalty_input.has_ghost_invoice else ''}）"
            ),
            "technical_detail": {
                "total_unpaid_principal": str(penalty_result.total_unpaid_principal),
                "admin_penalty": str(penalty_result.admin_penalty),
                "late_fee_total": str(penalty_result.late_fee_total),
                "ghost_invoice_penalty": str(penalty_result.ghost_invoice_penalty),
                "total_exposure": str(penalty_result.total_exposure),
                "severity": penalty_result.severity.value,
            },
        },
        [],  # 罚则依据为通用条文，不依赖具体风险标记
    )

    # ═══════════════════════════════════════════════════
    # 维度五：四流匹配风险量化
    # ═══════════════════════════════════════════════════
    # 沿用现有风险引擎的核心逻辑
    from app.core.four_flow_match import (
        calculate_four_flow_match,
        ContractRecord,
        InvoiceRecord,
        BankTransactionRecord,
    )

    # 注意：four_flow_match 的 Record 类型有严格字段定义
    from datetime import date as _date

    ct_records = [
        ContractRecord(
            contract_no=c.get("contract_no", ""),
            counterparty=c.get("counterparty", ""),
            amount=Decimal(str(c.get("contract_amount", 0))),
            signing_date=_date.today(),
        )
        for c in payload.contracts[:100]
    ]

    inv_records = [
        InvoiceRecord(
            invoice_no=inv.get("invoice_no", ""),
            invoice_type=inv.get("invoice_type", "output"),
            amount=Decimal(str(inv.get("amount", inv.get("total_amount", 0)))),
            total_amount=Decimal(str(inv.get("total_amount", 0))),
            buyer_name=inv.get("buyer_name", inv.get("counterparty", "")),
            seller_name=inv.get("seller_name", ""),
            product_name=inv.get("product_name", inv.get("goods_name", "")),
        )
        for inv in payload.invoices[:100]
    ]

    bk_records = [
        BankTransactionRecord(
            transaction_date=(
                tx.get("transaction_date")
                if isinstance(tx.get("transaction_date"), _date)
                else _date.today()
            ),
            amount=Decimal(str(tx.get("amount", 0))),
            direction=tx.get("direction", "inflow"),
            account_type=tx.get("account_type", "corporate"),
            counterparty=tx.get("counterparty", ""),
            description=tx.get("description", ""),
            is_declared=tx.get("is_declared", False),
        )
        for tx in payload.bank_transactions[:100]
    ]

    ffm_result = calculate_four_flow_match(ct_records, inv_records, bk_records)

    dim_scores["four_flow_match"] = 100.0 - float(ffm_result.overall_score)
    dim_details["four_flow_match"] = _with_policy_basis(
        "four_flow_match",
        {
            "score": dim_scores["four_flow_match"],
            "detail": f"四流匹配度 {ffm_result.overall_score:.0f} 分——合同、发票、资金、货物的一致性",
            "technical_detail": {
                "overall_score": ffm_result.overall_score,
                "contract_invoice_score": ffm_result.contract_invoice_score,
                "invoice_bank_score": ffm_result.invoice_bank_score,
                "counterparty_consistency_score": ffm_result.counterparty_consistency_score,
                "amount_consistency_score": ffm_result.amount_consistency_score,
            },
        },
        ffm_result.risk_flags,
    )
    result.risk_flags.extend(ffm_result.risk_flags)

    # ═══════════════════════════════════════════════════
    # 综合评分
    # ═══════════════════════════════════════════════════

    # 权重定义
    weights = {
        "macro_internal_control": 0.20,
        "vat_gaar": 0.25,
        "iit_hidden_dividend": 0.15,
        "compound_penalty": 0.15,
        "four_flow_match": 0.25,
    }

    overall = sum(
        dim_scores.get(dim, 0) * w
        for dim, w in weights.items()
    )
    result.overall_risk_score = round(overall, 2)

    # 取消重
    result.risk_flags = list(dict.fromkeys(result.risk_flags))
    result.recommendations = list(dict.fromkeys(result.recommendations))

    # 风险等级映射（5级）
    if result.overall_risk_score >= 80:
        result.overall_risk_level = "critical"
    elif result.overall_risk_score >= 60:
        result.overall_risk_level = "high"
    elif result.overall_risk_score >= 45:
        result.overall_risk_level = "medium_high"
    elif result.overall_risk_score >= 30:
        result.overall_risk_level = "medium"
    else:
        result.overall_risk_level = "low"

    # ── 一票否决规则 ──
    high_count = sum(1 for s in dim_scores.values() if s >= 70)
    if high_count >= 3 and result.overall_risk_score < 80:
        result.overall_risk_score = 80.0
        result.overall_risk_level = "critical"
    elif high_count >= 2 and result.overall_risk_score < 60:
        result.overall_risk_score = 60.0
        result.overall_risk_level = "high"

    result.dimension_scores = dim_scores
    result.dim_details = dim_details

    # ── 双语输出 ──
    result.business_narrative = _generate_comprehensive_narrative(result, payload)
    result.technical_summary = {
        "dimension_scores": dim_scores,
        "dimension_details": dim_details,
        "overall_score": result.overall_risk_score,
        "risk_level": result.overall_risk_level,
        "weights": weights,
        "flags_count": len(result.risk_flags),
        "veto_triggered": high_count >= 2,
        "thresholds": {
            "critical": 80,
            "high": 60,
            "medium_high": 45,
            "medium": 30,
        },
    }

    result.metadata = {
        "engine_version": "2.0.0",
        "assessment_dimensions": 5,
        "legal_basis": [
            "《税收征收管理法》第32条/第35条/第63条/第64条",
            "《增值税法》一般反避税条款",
            "《发票管理办法》第37条",
            "财税[2003]158号（股东借款视同分红）",
        ],
    }

    return result


# ═══════════════════════════════════════════════════════
# 双语叙述生成
# ═══════════════════════════════════════════════════════

def _generate_comprehensive_narrative(
    result: ComprehensiveTaxRiskResult,
    payload: EnterpriseDataPayload,
) -> str:
    """生成五维全景商业语言评估报告"""

    level_map = {
        "critical": "严重风险 · 红色警报",
        "high": "高风险 · 红色预警",
        "medium_high": "中高风险 · 橙色关注",
        "medium": "中等风险 · 黄色提示",
        "low": "低风险 · 绿色通行",
    }

    lines = [
        "═══════════════════════════════════════════════",
        f" 「税智·心判」五维全景税务风险评估报告",
        f" 企业：{payload.enterprise_name}",
        f" 行业：{payload.industry} ({'重资产' if payload.asset_type == 'heavy_asset' else '轻资产'})",
        f" 评估日期：{result.assessment_date[:10]}",
        "═══════════════════════════════════════════════",
        "",
        f"综合风险等级：{level_map.get(result.overall_risk_level, result.overall_risk_level)}",
        f"综合风险评分：{result.overall_risk_score:.1f} / 100",
        "",
    ]

    dim_names = {
        "macro_internal_control": "一、行业基准对标（异质性宏观内控）",
        "vat_gaar": "二、增值税 GAAR 反避税审查",
        "iit_hidden_dividend": "三、个税隐性分红穿透",
        "compound_penalty": "四、复合惩罚敞口推演",
        "four_flow_match": "五、四流匹配风险量化",
    }

    for dim, name in dim_names.items():
        score = result.dimension_scores.get(dim, 0)
        detail = result.dim_details.get(dim, {}).get("detail", "")
        status = "🟢" if score < 30 else ("🟡" if score < 60 else "🔴" if score < 80 else "⛔")
        lines.append(f"{status} {name}（{score:.0f}分）")
        lines.append(f"   {detail}")
        lines.append("")

    if result.risk_flags:
        lines.append(f"共发现 {len(result.risk_flags)} 个风险点：")
        for i, flag in enumerate(result.risk_flags[:10], 1):
            lines.append(f"  {i}. {flag}")
    else:
        lines.append("未发现重大财税合规风险。")

    if result.recommendations:
        lines.append("")
        lines.append("整改建议：")
        for i, rec in enumerate(result.recommendations[:5], 1):
            lines.append(f"  {i}. {rec}")

    if result.compound_penalty and result.compound_penalty.total_exposure > Decimal("0"):
        lines.append("")
        lines.append(f"预期总敞口：¥{result.compound_penalty.total_exposure:,.2f}")
        lines.append(f"  其中行政罚款：¥{result.compound_penalty.admin_penalty:,.2f}")
        lines.append(f"  其中滞纳金：  ¥{result.compound_penalty.late_fee_total:,.2f}")

    return "\n".join(lines)
