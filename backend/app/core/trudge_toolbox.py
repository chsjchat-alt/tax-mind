"""
Trudge 救赎工具箱

P3 增强模块，提供两个核心工具：
  1. 自查报告生成器 — 基于 compliance_checker 的 findings 自动生成 Markdown 报告
  2. 分期补税模拟 — 对比一次性补缴 vs 分期补缴的现金流影响

核心函数：
  generate_self_audit_report()  → 生成 Markdown 自查报告
  simulate_installment_payment() → 分期补税现金流对比
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field

_logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 自查报告生成器
# ═══════════════════════════════════════════════════════════════

class SelfAuditReport(BaseModel):
    """自查报告"""
    report_id: str = Field(..., description="报告编号")
    enterprise_name: str = Field(..., description="企业名称")
    industry: str = Field(..., description="行业")
    generated_at: str = Field(..., description="生成时间")
    findings_summary: dict = Field(default_factory=dict, description="发现摘要")
    findings_detail: list[dict] = Field(default_factory=list, description="详细发现")
    markdown_content: str = Field(default="", description="Markdown 完整报告")
    risk_level: str = Field(default="low", description="综合风险等级")
    compliance_advice: list[str] = Field(default_factory=list, description="合规建议清单")


def generate_self_audit_report(
    enterprise_name: str,
    industry: str,
    findings: list[dict],
    annual_revenue: float = 0,
    compliance_info: Optional[dict] = None,
    risk_score: float = 0,
    risk_level: str = "low",
) -> SelfAuditReport:
    """
    基于 compliance_checker 的 findings 生成 Markdown 自查报告。

    Args:
        enterprise_name: 企业名称
        industry: 所属行业
        findings: 合规校验发现列表（来自 run_compliance_check）
        annual_revenue: 年营收
        compliance_info: 合规调整信息（reduction_pct, is_fully_compliant 等）
        risk_score: 风险评分
        risk_level: 风险等级

    Returns:
        SelfAuditReport: 包含 Markdown 全文的自查报告
    """
    now = date.today()
    report_id = f"ZC-{now.strftime('%Y%m%d')}-{enterprise_name[:4] if enterprise_name else 'XXXX'}"

    # ── 分类统计 ──
    high_count = sum(1 for f in findings if f.get("severity") == "high")
    medium_count = sum(1 for f in findings if f.get("severity") == "medium")
    low_count = sum(1 for f in findings if f.get("severity") == "low")
    total_count = len(findings)

    categories: dict[str, list] = {}
    for f in findings:
        cat = f.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f)

    category_map = {"tax": "税务合规", "accounting": "会计核算", "financial": "财务比率", "invoice": "发票管理", "other": "其他"}

    # ── 综合评级 ──
    if high_count >= 3 or risk_level == "critical":
        overall_rating = "高风险 — 存在多项严重不合规问题，建议立即整改"
    elif high_count >= 1 or risk_level in ("high", "medium_high"):
        overall_rating = "中高风险 — 存在不合规问题，建议尽快整改"
    elif medium_count >= 2:
        overall_rating = "中等风险 — 存在部分不合规事项，建议限期整改"
    elif medium_count >= 1 or low_count >= 3:
        overall_rating = "关注级 — 存在轻微不合规事项，建议自查改进"
    else:
        overall_rating = "正常 — 未发现明显不合规事项，请保持合规经营"

    # ── 整改建议 ──
    compliance_advice = []
    if high_count > 0:
        compliance_advice.append(f"立即处理 {high_count} 项高风险发现，建议在30天内完成整改")
    if medium_count > 0:
        compliance_advice.append(f"限期处理 {medium_count} 项中风险发现，建议在90天内完成整改")
    if low_count > 0:
        compliance_advice.append(f"持续关注 {low_count} 项低风险事项，纳入日常自查清单")
    compliance_advice.append("建议委托专业税务顾问进行年度税务健康检查")
    compliance_advice.append("建立健全内部税务风险管理制度，定期开展自查自纠")

    # ── 生成 Markdown 报告 ──
    md_lines = [
        f"# 企业税务合规自查报告",
        f"",
        f"**报告编号**: {report_id}",
        f"**企业名称**: {enterprise_name}",
        f"**所属行业**: {industry}",
        f"**年营业收入**: {annual_revenue:,.0f} 元" if annual_revenue > 0 else "**年营业收入**: （未登记）",
        f"**生成日期**: {now.strftime('%Y年%m月%d日')}",
        f"**风险评分**: {risk_score:.1f}/100" if risk_score > 0 else "**风险评分**: 待评估",
        f"",
        f"---",
        f"",
        f"## 一、自查综述",
        f"",
        f"**综合评级**: {overall_rating}",
        f"",
        f"本次自查共发现 **{total_count}** 项不合规事项，其中高风险 **{high_count}** 项、",
        f"中风险 **{medium_count}** 项、低风险 **{low_count}** 项。",
        f"",
    ]

    # 合规调整信息
    if compliance_info:
        reduc_pct = compliance_info.get("reduction_pct", 0) * 100
        is_fully = compliance_info.get("is_fully_compliant", False)
        adj_level = compliance_info.get("adjusted_level", risk_level)
        md_lines.append(f"**合规完成度**: {reduc_pct:.0f}% | **调整后风险等级**: {adj_level}")
        if is_fully:
            md_lines.append(f"**状态**: 已完全合规")
        md_lines.append(f"")

    # ── 分类详细 ──
    md_lines.append(f"## 二、分项自查结果")
    md_lines.append(f"")

    for cat_key, cat_findings in categories.items():
        cat_name = category_map.get(cat_key, cat_key)
        md_lines.append(f"### {cat_name}（{len(cat_findings)} 项）")
        md_lines.append(f"")

        for i, f in enumerate(cat_findings, 1):
            sev = f.get("severity", "low")
            sev_label = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}.get(sev, "⚪ 未知")
            title = f.get("title", "未命名发现")
            desc = f.get("description", "")
            sugg = f.get("suggestion", "")

            md_lines.append(f"#### {i}. {sev_label} — {title}")
            md_lines.append(f"")
            md_lines.append(f"**问题描述**: {desc}")
            md_lines.append(f"")
            md_lines.append(f"**整改建议**: {sugg}")
            md_lines.append(f"")
            # 指标数据
            metrics = f.get("metrics", {})
            if metrics:
                md_lines.append(f"**相关指标**:")
                md_lines.append(f"")
                for mk, mv in metrics.items():
                    if isinstance(mv, float):
                        md_lines.append(f"- {mk}: {mv:.2f}")
                    else:
                        md_lines.append(f"- {mk}: {mv}")
                md_lines.append(f"")

    # ── 合规建议 ──
    md_lines.append(f"## 三、合规整改建议")
    md_lines.append(f"")
    for i, advice in enumerate(compliance_advice, 1):
        md_lines.append(f"{i}. {advice}")
    md_lines.append(f"")

    # ── 声明 ──
    md_lines.append(f"---")
    md_lines.append(f"")
    md_lines.append(f"## 四、免责声明")
    md_lines.append(f"")
    md_lines.append(f"本报告由税智·心判系统基于财务数据自动生成，仅供企业内部税务自查参考。")
    md_lines.append(f"本报告不构成正式的法律或税务意见，具体税务处理方案请咨询专业税务顾问。")
    md_lines.append(f"建议企业将本报告作为年度税务自查的依据之一存档备查。")
    md_lines.append(f"")

    markdown = "\n".join(md_lines)

    findings_summary = {
        "total": total_count,
        "high": high_count,
        "medium": medium_count,
        "low": low_count,
        "by_category": {category_map.get(k, k): len(v) for k, v in categories.items()},
        "overall_rating": overall_rating,
    }

    return SelfAuditReport(
        report_id=report_id,
        enterprise_name=enterprise_name,
        industry=industry,
        generated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        findings_summary=findings_summary,
        findings_detail=[f for f in findings],
        markdown_content=markdown,
        risk_level=risk_level,
        compliance_advice=compliance_advice,
    )


# ═══════════════════════════════════════════════════════════════
# 分期补税模拟引擎
# ═══════════════════════════════════════════════════════════════

class InstallmentScenario(BaseModel):
    """单个分期方案"""
    months: int = Field(..., description="分期月数")
    monthly_payment: float = Field(..., description="每月应缴金额（含滞纳金）")
    total_installment_payment: float = Field(..., description="分期总支付")
    total_interest_cost: float = Field(..., description="分期比一次性多付的滞纳金")
    payoff_date: str = Field(..., description="预计还清日期")
    cash_flow_rating: str = Field(..., description="现金流友好度评分")


class InstallmentComparison(BaseModel):
    """一次性 vs 分期对比结果"""
    total_tax_due: float = Field(..., description="应补税款总额")
    late_fee_daily: float = Field(..., description="每日滞纳金")
    lump_sum: dict = Field(default_factory=dict, description="一次性补缴方案")
    installments: list[dict] = Field(default_factory=list, description="分期方案列表")
    recommendation: str = Field(default="", description="分期方案推荐")
    cash_flow_analysis: str = Field(default="", description="现金流分析")


def simulate_installment_payment(
    total_tax_due: float,
    comprehensive_tax_rate: float = 0.06,
    annual_revenue: float = 0,
    overdue_days: int = 0,
) -> InstallmentComparison:
    """
    对比一次性补缴 vs 分期补缴的现金流影响。

    分期逻辑：
      - 3 期（3个月）: 每月加收当月滞纳金
      - 6 期（6个月）: 每月加收当月滞纳金
      - 12 期（12个月）: 每月加收当月滞纳金

    滞纳金 = 日万分之五 = 0.05%/天 = 1.5%/月
    """
    # 日滞纳金率 = 0.0005 (日万分之五)
    daily_rate = 0.0005
    monthly_rate = daily_rate * 30  # 约 1.5%/月

    # 每日滞纳金额
    late_fee_daily = round(total_tax_due * daily_rate, 2)

    # ── 一次性补缴 ──
    if overdue_days > 0:
        lump_total = round(total_tax_due * (1 + daily_rate * overdue_days), 2)
        lump_late = round(total_tax_due * daily_rate * overdue_days, 2)
    else:
        lump_total = total_tax_due
        lump_late = 0.0

    lump_sum = {
        "payment_amount": lump_total,
        "late_fee": lump_late,
        "description": (
            f"一次性补缴 {total_tax_due:,.0f} 元" +
            (f"（含 {overdue_days} 天滞纳金 {lump_late:,.0f} 元）" if overdue_days > 0 else "")
        ),
        "cash_flow_impact": "大额一次性支出，对现金流冲击最大",
        "pros": ["最快结清欠税", "滞纳金总额最少", "风险彻底消除"],
        "cons": ["一次性现金支出压力大", "可能影响当月经营周转"],
    }

    # ── 分期方案 ──
    installment_options = [3, 6, 12]
    monthly_income = annual_revenue / 12 if annual_revenue > 0 else total_tax_due / 3

    installment_results = []
    for months in installment_options:
        monthly_principal = total_tax_due / months
        total_interest = 0.0
        remaining = total_tax_due

        for m in range(months):
            month_interest = remaining * monthly_rate
            total_interest += month_interest
            remaining -= monthly_principal

        monthly_payment = (total_tax_due + total_interest) / months
        total_install = total_tax_due + total_interest

        # 现金流评级
        payment_to_income = monthly_payment / monthly_income if monthly_income > 0 else 1.0
        if payment_to_income < 0.1:
            cash_rating = "极优 — 月供仅占营收 {:.0f}%".format(payment_to_income * 100)
        elif payment_to_income < 0.25:
            cash_rating = "良好 — 月供占营收 {:.0f}%".format(payment_to_income * 100)
        elif payment_to_income < 0.5:
            cash_rating = "可承受 — 月供占营收 {:.0f}%，需合理安排资金".format(payment_to_income * 100)
        else:
            cash_rating = "压力较大 — 月供占营收 {:.0f}%，建议延长分期或增加营收".format(payment_to_income * 100)

        payoff_date = (date.today() + timedelta(days=months * 30)).strftime("%Y年%m月")

        installment_results.append({
            "months": months,
            "monthly_payment": round(monthly_payment, 2),
            "total_installment_payment": round(total_install, 2),
            "total_interest_cost": round(total_interest, 2),
            "extra_vs_lump_sum": round(total_install - lump_total, 2),
            "payoff_date": payoff_date,
            "cash_flow_rating": cash_rating,
            "pros": [
                f"月付仅 {monthly_payment:,.0f} 元",
                "分散资金压力",
                "保障日常经营流动性",
            ],
            "cons": [f"多付滞纳金 {total_interest:,.0f} 元"],
        })

    # ── 智能推荐 ──
    if monthly_income > 0:
        lump_ratio = lump_total / monthly_income
        if lump_ratio < 0.5:
            recommendation = (
                f"推荐【一次性补缴】：应补税款仅占月营收 {lump_ratio:.0%}，"
                f"一次性结清可节省 {installment_results[0]['total_interest_cost']:,.0f} 元滞纳金"
            )
        elif lump_ratio < 1.5:
            recommendation = (
                f"推荐【3期分期】：月供 {installment_results[0]['monthly_payment']:,.0f} 元，"
                f"占月营收 {installment_results[0]['monthly_payment']/monthly_income:.0%}，"
                f"比6期少付 {installment_results[1]['total_interest_cost'] - installment_results[0]['total_interest_cost']:,.0f} 元滞纳金"
            )
        else:
            recommendation = (
                f"推荐【6期分期】：月供 {installment_results[1]['monthly_payment']:,.0f} 元，"
                f"平衡资金压力与滞纳金成本"
            )
    else:
        recommendation = "建议根据企业实际现金流选择合适的方案"

    cash_flow_analysis = ""
    if annual_revenue > 0:
        cash_flow_analysis = (
            f"企业年营收 {annual_revenue:,.0f} 元，月均 {monthly_income:,.0f} 元。"
            f"应补税款占年营收 {(total_tax_due/annual_revenue*100):.1f}%。"
        )

    return InstallmentComparison(
        total_tax_due=total_tax_due,
        late_fee_daily=late_fee_daily,
        lump_sum=lump_sum,
        installments=installment_results,
        recommendation=recommendation,
        cash_flow_analysis=cash_flow_analysis,
    )
