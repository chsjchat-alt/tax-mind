"""
复合罚款与滞纳金推演引擎 (penalty_calculator.py)

依据《中华人民共和国税收征收管理法》第32条、第63条、第64条
及《中华人民共和国发票管理办法》第37条，对企业的欠税本金
进行毁灭性罚款与滞纳金推演。

技术红线：
  1. 所有数值运算强制使用 decimal.Decimal（禁止 float）
  2. 输出为结构化 dict，包含枚举标记
  3. 输出双语（商业语言 + 财务技术语言）
  4. 严禁在此模块调用任何大模型 API 进行文本推演

规则来源：
  ─ 行政罚款：征管法第63条（偷税 0.5-5倍），第64条（不申报 0.5-5倍）
  ─ 滞纳金：征管法第32条（日万分之五，从滞纳税款之日起计算）
  ─ 发票罚款：发票管理办法第37条（虚开 1-5倍）
  ─ 个税穿透：穿透公私账户后识别未代扣代缴个人所得税，按20%还原
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Any


# ═══════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════

class PenaltyRiskLevel(StrEnum):
    """惩罚推演用风险等级（三档制）"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PenaltySeverity(StrEnum):
    """惩罚严重程度标记"""
    NORMAL = "normal"           # 常规：仅滞纳金，无罚款
    WARNING = "warning"         # 预警：滞纳金 + 0.5倍罚款
    SEVERE = "severe"           # 严重：滞纳金 + 1.5倍罚款
    DESTRUCTIVE = "destructive" # 毁灭性：滞纳金 + 3.5倍罚款
    CATACLYSMIC = "cataclysmic" # 灾难性：虚开 + 偷税叠加


# ═══════════════════════════════════════════════════════
# 常量（征管法硬编码参数）
# ═══════════════════════════════════════════════════════

# ── 滞纳金日利率：征管法第32条 ──
LATE_FEE_DAILY_RATE: Decimal = Decimal("0.0005")

# ── 个税隐性分红还原税率：利息、股息、红利所得 ──
IIT_DIVIDEND_RATE: Decimal = Decimal("0.20")

# ── 罚款倍数映射（风险等级 → 倍数） ──
# 低风险：0.5倍（首次违规从轻处罚）
# 中风险：1.5倍（征管法第63条标准罚款）
# 中高风险：2.5倍（多项指标偏离 + 故意倾向）
# 高风险：3.5倍（严重情节 + 发票虚开叠加）
# 严重风险：5.0倍（顶格处罚）
PENALTY_MULTIPLIER: dict[str, Decimal] = {
    "low": Decimal("0.5"),
    "medium": Decimal("1.5"),
    "medium_high": Decimal("2.5"),
    "high": Decimal("3.5"),
    "critical": Decimal("5.0"),
}

# ── 虚开发票额外罚款倍数 ──
GHOST_INVOICE_MULTIPLIER: Decimal = Decimal("2.0")


# ═══════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════

@dataclass
class UnpaidTaxInput:
    """欠税本金输入"""
    unpaid_vat: Decimal = Decimal("0")      # 未缴增值税
    unpaid_cit: Decimal = Decimal("0")      # 未缴企业所得税
    unpaid_iit: Decimal = Decimal("0")      # 穿透推算的未代扣代缴个税（隐性分红还原）
    unpaid_other: Decimal = Decimal("0")    # 其他未缴税款（印花税、附加税费等）
    late_days: int = 0                      # 滞纳天数预测
    risk_level: str = "medium"              # low / medium / high / critical
    has_ghost_invoice: bool = False         # 是否存在虚开发票嫌疑


@dataclass
class CompoundPenaltyResult:
    """复合罚款推演结果"""
    # ── 本金分解 ──
    total_unpaid_principal: Decimal = Decimal("0")    # 欠税本金合计
    unpaid_vat: Decimal = Decimal("0")
    unpaid_cit: Decimal = Decimal("0")
    unpaid_iit: Decimal = Decimal("0")                # 个税穿透欠税

    # ── 行政罚款 ──
    penalty_multiplier: Decimal = Decimal("0")        # 适用罚款倍数
    admin_penalty: Decimal = Decimal("0")             # 行政罚款额

    # ── 滞纳金 ──
    late_days: int = 0
    late_fee_daily_rate: Decimal = LATE_FEE_DAILY_RATE
    late_fee_total: Decimal = Decimal("0")            # 滞纳金总额（单利复现累加）
    late_fee_breakdown: dict[str, Decimal] = field(default_factory=dict)

    # ── 虚开叠加 ──
    has_ghost_invoice: bool = False
    ghost_invoice_penalty: Decimal = Decimal("0")

    # ── 总敞口 ──
    total_exposure: Decimal = Decimal("0")            # 总敞口 = 本金 + 罚款 + 滞纳金 + 虚开

    # ── 枚举标记 ──
    severity: PenaltySeverity = PenaltySeverity.NORMAL
    risk_level: str = "medium"

    # ── 双语输出 ──
    business_narrative: str = ""                       # 商业语言（老板能看懂的）
    technical_narrative: str = ""                     # 财务技术语言

    # ── 元数据 ──
    metadata: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════
# 核心函数
# ═══════════════════════════════════════════════════════

def _calculate_iit_hidden_dividend(
    shareholder_loan_amount: Decimal,
    days_overdue: int = 365,
) -> Decimal:
    """
    个税隐性分红穿透还原。

    依据：财税[2003]158号——股东从其投资企业借款，在
    该纳税年度终了后既不归还又未用于企业生产经营的，
    其未归还的借款可视为企业对个人投资者的红利分配，
    依照"利息、股息、红利所得"项目计征个人所得税。

    Args:
        shareholder_loan_amount: 股东借款余额（其他应收款明
            细中筛选出的股东及其直系亲属借款）
        days_overdue: 超过365天的逾期天数（用于判断是否触发
            穿透规则，非计息参数）

    Returns:
        应补缴的个人所得税额（= 借款总额 × 20%）
    """
    # 第1条约束：借款必须满365天未归还才触发穿透
    if days_overdue < 365 or shareholder_loan_amount <= Decimal("0"):
        return Decimal("0")

    # 第2条约束：按"利息、股息、红利所得"20%固定税率计算
    unpaid_iit = shareholder_loan_amount * IIT_DIVIDEND_RATE
    return unpaid_iit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_compound_penalty_exposure(
    unpaid_tax: UnpaidTaxInput,
) -> CompoundPenaltyResult:
    """
    毁灭性惩罚推演主函数。

    按征管法第32条、第63条、第64条及发票管理办法第37条，
    对企业欠税本金进行行政罚款、滞纳金、虚开发票罚款的
    复合推演，输出结构化结果。

    规则索引：
      - 征管法第32条：滞纳金 = 欠税本金 × 0.0005/日 × 滞纳天数
      - 征管法第63条：偷税罚款 0.5-5 倍
      - 征管法第64条：不申报罚款 0.5-5 倍
      - 发票管理办法第37条：虚开发票罚款 1-5 倍

    Args:
        unpaid_tax: 欠税本金输入

    Returns:
        CompoundPenaltyResult: 结构化复合罚款推演结果
    """
    result = CompoundPenaltyResult()

    # ── Step 1: 本金汇总 ─────────────────────────────────
    principal = (
        unpaid_tax.unpaid_vat +
        unpaid_tax.unpaid_cit +
        unpaid_tax.unpaid_iit +
        unpaid_tax.unpaid_other
    )
    result.total_unpaid_principal = principal.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    result.unpaid_vat = unpaid_tax.unpaid_vat
    result.unpaid_cit = unpaid_tax.unpaid_cit
    result.unpaid_iit = unpaid_tax.unpaid_iit
    result.late_days = unpaid_tax.late_days
    result.risk_level = unpaid_tax.risk_level

    # ── Step 2: 行政罚款 ─────────────────────────────────
    # 依据：征管法第63条/第64条——罚款倍数映射
    multiplier = PENALTY_MULTIPLIER.get(
        unpaid_tax.risk_level, Decimal("1.5")
    )
    result.penalty_multiplier = multiplier

    # 行政罚款额 = 总欠税本金 × 罚款倍数
    admin_penalty = (principal * multiplier).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    result.admin_penalty = admin_penalty

    # ── Step 3: 滞纳金（征管法第32条） ────────────────────
    # 滞纳金 = 欠税本金 × 日万分之五 × 滞纳天数
    # 单利复现累加（每日等额累加，非复利）
    # 注：principal 已包含 unpaid_iit（双计数 bug 修复），无需额外加回
    late_fee_base = principal
    late_fee_total = (
        late_fee_base *
        LATE_FEE_DAILY_RATE *
        Decimal(str(unpaid_tax.late_days))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    result.late_fee_total = late_fee_total

    # 分解各税种滞纳金
    result.late_fee_breakdown = {
        "vat_late_fee": (
            unpaid_tax.unpaid_vat * LATE_FEE_DAILY_RATE *
            Decimal(str(unpaid_tax.late_days))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "cit_late_fee": (
            unpaid_tax.unpaid_cit * LATE_FEE_DAILY_RATE *
            Decimal(str(unpaid_tax.late_days))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "iit_late_fee": (
            unpaid_tax.unpaid_iit * LATE_FEE_DAILY_RATE *
            Decimal(str(unpaid_tax.late_days))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "other_late_fee": (
            unpaid_tax.unpaid_other * LATE_FEE_DAILY_RATE *
            Decimal(str(unpaid_tax.late_days))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    }

    # ── Step 4: 虚开发票叠加（发票管理办法第37条） ───────
    result.has_ghost_invoice = unpaid_tax.has_ghost_invoice
    if unpaid_tax.has_ghost_invoice:
        result.ghost_invoice_penalty = (
            unpaid_tax.unpaid_vat * GHOST_INVOICE_MULTIPLIER
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        result.ghost_invoice_penalty = Decimal("0")

    # ── Step 5: 总敞口 ────────────────────────────────────
    result.total_exposure = (
        principal +
        admin_penalty +
        late_fee_total +
        result.ghost_invoice_penalty
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ── Step 6: 严重程度标记 ──────────────────────────────
    if unpaid_tax.has_ghost_invoice and multiplier >= Decimal("3.5"):
        result.severity = PenaltySeverity.CATACLYSMIC
    elif multiplier >= Decimal("3.5"):
        result.severity = PenaltySeverity.DESTRUCTIVE
    elif multiplier >= Decimal("1.5"):
        result.severity = PenaltySeverity.SEVERE
    elif multiplier >= Decimal("0.5"):
        result.severity = PenaltySeverity.WARNING
    else:
        result.severity = PenaltySeverity.NORMAL

    # ── Step 7: 双语输出 ──────────────────────────────────
    result.business_narrative = _generate_business_narrative(result)
    result.technical_narrative = _generate_technical_narrative(result)

    # ── Step 8: 元数据 ────────────────────────────────────
    result.metadata = {
        "legal_basis": [
            "征管法第32条（滞纳金日万分之五）",
            "征管法第63条（偷税罚款0.5-5倍）",
            "征管法第64条（不申报罚款0.5-5倍）",
            "发票管理办法第37条（虚开发票罚款1-5倍）",
            "财税[2003]158号（股东借款视同分红）",
        ],
        "calculation_params": {
            "late_fee_daily_rate": str(LATE_FEE_DAILY_RATE),
            "iit_dividend_rate": str(IIT_DIVIDEND_RATE),
            "penalty_multiplier_applied": str(multiplier),
        },
    }

    return result


# ═══════════════════════════════════════════════════════
# 双语叙述生成（纯模板，不调用大模型）
# ═══════════════════════════════════════════════════════

def _generate_business_narrative(result: CompoundPenaltyResult) -> str:
    """生成商业语言叙述（老板能看懂的）"""

    severity_map = {
        PenaltySeverity.NORMAL: "正常",
        PenaltySeverity.WARNING: "预警（首次违规从轻处罚）",
        PenaltySeverity.SEVERE: "严重（偷税标准处罚）",
        PenaltySeverity.DESTRUCTIVE: "毁灭性（严重情节叠加）",
        PenaltySeverity.CATACLYSMIC: "灾难性（偷税+虚开叠加）",
    }

    lines = [
        "═══════════════════════════════════════",
        "    「税智·心判」惩罚推演报告",
        "═══════════════════════════════════════",
        "",
        f"欠税本金合计：¥{result.total_unpaid_principal:,.2f}",
        f"  其中未缴增值税：   ¥{result.unpaid_vat:,.2f}",
        f"  其中未缴企业所得税：¥{result.unpaid_cit:,.2f}",
        f"  其中个税穿透欠税：  ¥{result.unpaid_iit:,.2f}",
        "",
        f"风险等级：{result.risk_level}",
        f"处罚严重程度：{severity_map.get(result.severity, str(result.severity))}",
        "",
        f"行政罚款（{result.penalty_multiplier}倍）：¥{result.admin_penalty:,.2f}",
        f"滞纳金（{result.late_days}天×万分之五/日）：¥{result.late_fee_total:,.2f}",
    ]

    if result.has_ghost_invoice:
        lines.append(
            f"虚开发票额外罚款（2倍）：¥{result.ghost_invoice_penalty:,.2f}"
        )

    lines.extend([
        "",
        f"═══════════════════════════════════════",
        f"预计总敞口：¥{result.total_exposure:,.2f}",
        f"═══════════════════════════════════════",
    ])

    return "\n".join(lines)


def _generate_technical_narrative(result: CompoundPenaltyResult) -> str:
    """生成财务技术语言叙述"""

    lines = [
        "[TECHNICAL] Compound Penalty Exposure Calculation",
        f"principal={result.total_unpaid_principal}",
        f"vat_principal={result.unpaid_vat} cit_principal={result.unpaid_cit}",
        f"iit_penetration={result.unpaid_iit}",
        f"risk_level={result.risk_level} multiplier={result.penalty_multiplier}",
        f"admin_penalty={result.admin_penalty}",
        f"late_days={result.late_days} daily_rate={LATE_FEE_DAILY_RATE} late_fee={result.late_fee_total}",
        f"ghost_invoice_penalty={result.ghost_invoice_penalty}",
        f"total_exposure={result.total_exposure}",
        f"severity={result.severity.value}",
        "",
        "Legal basis:",
        "  征管法第32条 (late fee = principal * 0.0005 * days)",
        "  征管法第63条 (tax evasion penalty 0.5-5x)",
        "  发票管理办法第37条 (ghost invoice 1-5x)",
        f"  Penalty formula: {result.total_unpaid_principal} * {result.penalty_multiplier} = {result.admin_penalty}",
        f"  Late fee formula: ({result.total_unpaid_principal} + {result.unpaid_iit}) * 0.0005 * {result.late_days} = {result.late_fee_total}",
    ]

    return "\n".join(lines)
