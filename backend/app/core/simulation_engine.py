"""
沉浸式风险模拟器

基于前景理论的"损失框架"——通过模拟"继续当前模式"vs"合规整改"两条路径的财务后果对比，
改变老板的风险感知，推动主动合规。

模拟逻辑：
  路径A（继续不合规）：每月隐匿收入 → 少缴税款累积 → 稽查概率递增 → 期望罚款+滞纳金
  路径B（合规整改）：一次性补缴 + 服务费 → 之后正常纳税

三个时间节点：6个月、1年、3年

稽查概率矩阵（基于风险等级）：
                     6个月    1年     3年
  低风险             5%      10%     20%
  中风险            15%      25%     45%
  高风险            30%      50%     80%

增强模块（Budge 升级 - 损失具象化）：
  1. 第三方后果关联：招投标资格/银行授信/政府补贴受限时间
  2. 同行对比压力：动态查询本区同行立案数及处罚分布
  3. 模拟官方文书：生成仿《税务事项通知书》格式的第三方风险提示

商业语言输出：损失框架话术（不说"合规能省多少"，说"不合规会损失多少"）
技术语言输出：结构化对比数据
"""

import json
import math
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# ── 罚款倍数（从 penalty_calculator 导入，单一权威来源） ──
from app.core.penalty_calculator import PENALTY_MULTIPLIER

# ── 稽查概率矩阵 ──
AUDIT_PROBABILITY_MATRIX = {
    "low": {
        "6months": 0.05, "1year": 0.10, "2years": 0.15, "3years": 0.20,
    },
    "medium": {
        "6months": 0.15, "1year": 0.25, "2years": 0.35, "3years": 0.45,
    },
    "medium_high": {
        "6months": 0.25, "1year": 0.40, "2years": 0.55, "3years": 0.65,
    },
    "high": {
        "6months": 0.30, "1year": 0.50, "2years": 0.65, "3years": 0.80,
    },
    "critical": {
        "6months": 0.50, "1year": 0.75, "2years": 0.88, "3years": 0.95,
    },
}

# ── 滞纳金日利率 ──
LATE_FEE_DAILY_RATE = 0.0005

# 时间节点对应的月数和天数
PERIOD_CONFIG = {
    "6months": {"months": 6, "days": 180},
    "1year": {"months": 12, "days": 365},
    "3years": {"months": 36, "days": 1095},
}


class SimulationInput(BaseModel):
    """模拟器输入"""
    monthly_hidden_revenue: float = Field(..., ge=0, description="每月隐匿收入金额（元）")
    comprehensive_tax_rate: float = Field(..., ge=0, le=1, description="综合税率（如0.06表示6%）")
    risk_level: Literal["low", "medium", "medium_high", "high", "critical"] = Field(
        ..., description="风险等级（五级）"
    ),
    remediation_cost: float = Field(..., ge=0, description="一次性整改成本（补缴+服务费，元）")
    monthly_reputation_loss: float = Field(default=0.0, ge=0, description="高风险时每月声誉损失（元）")
    industry: str = Field(default="批发零售", description="所属行业")


class TimePointResult(BaseModel):
    """单时间节点结果"""
    period: str                                                  # "6months" / "1year" / "3years"
    months_elapsed: int                                          # 经过月数
    path_a_cost: float                                           # 路径A总成本
    path_b_cost: float                                           # 路径B总成本
    audit_probability: float                                     # 稽查概率
    expected_penalty: float                                      # 期望罚款
    expected_late_fee: float                                     # 期望滞纳金
    cost_difference: float                                       # 路径A - 路径B（正值=不合规更贵）
    total_hidden_tax: float = 0.0                                # 累计少缴税款


class SimulationResult(BaseModel):
    """模拟器总结果"""
    time_points: list[TimePointResult]                           # 三个时间节点结果
    recommendation: str                                          # 推荐建议
    loss_frame_message: str                                      # 损失框架话术
    case_references: list[str] = Field(default_factory=list)     # 脱敏案例引用
    technical_summary: dict = Field(default_factory=dict)        # 技术摘要


def _load_case_references(industry: str) -> list[str]:
    """加载同行业脱敏案例引用"""
    import json
    from pathlib import Path

    case_path = Path(__file__).parent.parent / "data" / "case_studies.json"
    references = []
    try:
        with open(case_path, "r", encoding="utf-8") as f:
            cases = json.load(f)
        # 匹配同行业案例
        matched = [c for c in cases if c.get("industry") == industry]
        if not matched:
            matched = cases[:3]  # 无匹配时取前3个
        for c in matched[:3]:
            ref = f"【{c['case_id']}】{c['industry']}企业，{c['violation']}，查处结果：{c['result']}，罚款{c['penalty_amount']}"
            references.append(ref)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        references = [
            "【XJ-2024-001】某商贸企业通过私卡收款隐匿收入480万元，被金税四期系统自动比对发现，补税+罚款+滞纳金合计约310万元。",
            "【XJ-2024-002】某制造企业虚列成本费用230万元，被税务稽查查实，补税+罚款合计约150万元。",
            "【XJ-2024-003】某电商企业少申报收入1200万元，稽查后补税+罚款合计约800万元。",
        ]
    return references


def _generate_loss_frame(result: SimulationResult, data: SimulationInput) -> str:
    """生成损失框架话术"""
    risk = data.risk_level
    remediation = data.remediation_cost

    # 找到3年节点的数据（最后一个时间点）
    last_point = result.time_points[-1] if result.time_points else None

    if last_point is None:
        return "暂无足够数据进行风险模拟。"

    # 格式化金额为万元
    def _fmt(val: float) -> str:
        return f"{val/10000:.1f}万元" if val >= 10000 else f"{val:,.0f}元"

    if last_point.path_a_cost <= 0 and remediation <= 0:
        return "当前未发现明显的风险敞口，请继续保持合规经营。"

    if risk == "critical":
        ratio_pct = remediation / last_point.path_a_cost * 100 if last_point.path_a_cost > 0 else 0
        return (
            f"⚠️ 最高警报：按当前模式继续经营，3年内被稽查的概率高达 {last_point.audit_probability:.0%}，"
            f"预计将面临罚款及滞纳金约 {_fmt(last_point.path_a_cost)}。"
            f"而现在进行合规整改的成本仅为 {_fmt(remediation)}，"
            f"是未来可能代价的 {ratio_pct:.0f}%。"
            f"立即停止所有高风险行为，马上启动全面合规整改——刻不容缓！"
        )
    elif risk == "high":
        ratio_pct = remediation / last_point.path_a_cost * 100 if last_point.path_a_cost > 0 else 0
        return (
            f"按当前模式继续经营，3年内被稽查的概率高达 {last_point.audit_probability:.0%}，"
            f"预计将面临罚款及滞纳金约 {_fmt(last_point.path_a_cost)}。"
            f"而现在进行合规整改的成本仅为 {_fmt(remediation)}，"
            f"是未来可能代价的 {ratio_pct:.0f}%。"
            f"拖延一天，滞纳金就在滚动累积——立即行动，把主动权握在自己手里。"
        )
    elif risk == "medium_high":
        return (
            f"按当前模式继续经营，1年内被稽查概率 {result.time_points[1].audit_probability:.0%}，"
            f"3年内升至 {last_point.audit_probability:.0%}，"
            f"预计将面临总代价约 {_fmt(last_point.path_a_cost)}。"
            f"及早整改成本为 {_fmt(remediation)}，"
            f"建议优先启动整改以控制风险敞口。"
        )
    elif risk == "medium":
        return (
            f"按当前模式继续经营，1年内被稽查的概率为 {result.time_points[1].audit_probability:.0%}，"
            f"3年内升至 {last_point.audit_probability:.0%}。"
            f"预计将面临罚款及滞纳金约 {_fmt(last_point.path_a_cost)}。"
            f"及早整改的成本为 {_fmt(remediation)}，"
            f"远低于被稽查后的总代价。建议尽快启动合规整改。"
        )
    else:
        return (
            f"当前风险水平较低，但仍存在约 {_fmt(result.time_points[0].path_a_cost)} "
            f"的潜在风险敞口（6个月）。合规经营是企业长期发展的基石，"
            f"建议保持警惕，防患于未然。"
        )


def _compute_dynamic_risk_level(monthly_hidden_revenue: float) -> str:
    """
    根据场景参数动态计算风险等级。
    
    月均隐匿收入（元）→ 风险等级：
          0               low
      < 50,000         medium
      < 200,000        medium_high
      < 500,000        high
      >= 500,000       critical
    """
    if monthly_hidden_revenue <= 0:
        return "low"
    if monthly_hidden_revenue < 50_000:
        return "medium"
    if monthly_hidden_revenue < 200_000:
        return "medium_high"
    if monthly_hidden_revenue < 500_000:
        return "high"
    return "critical"


def run_simulation(data: SimulationInput) -> SimulationResult:
    """
    运行沉浸式风险模拟，对比合规与不合规两条路径的财务后果。

    Args:
        data: 模拟器输入数据

    Returns:
        SimulationResult: 三个时间节点的对比结果和合规干预话术

    Edge Cases:
      - 隐匿收入为 0：所有期望成本为 0
      - 综合税率为 0：少缴税款为 0
      - 整改成本为 0：路径B成本为 0
    """
    monthly_tax_hidden = data.monthly_hidden_revenue * data.comprehensive_tax_rate
    multiplier = float(PENALTY_MULTIPLIER.get(data.risk_level, Decimal("1.5")))

    time_points = []
    for period_key in ["6months", "1year", "3years"]:
        cfg = PERIOD_CONFIG[period_key]
        months = cfg["months"]
        days = cfg["days"]

        # 累计少缴税款
        total_hidden_tax = round(monthly_tax_hidden * months, 2)

        # 稽查概率
        audit_prob = AUDIT_PROBABILITY_MATRIX.get(data.risk_level, {}).get(period_key, 0.10)

        # 路径A：期望罚款 + 期望滞纳金
        expected_penalty = round(total_hidden_tax * multiplier * audit_prob, 2)
        expected_late_fee = round(total_hidden_tax * LATE_FEE_DAILY_RATE * days * audit_prob, 2)

        # 高风险/严重风险时计入声誉损失
        reputation_loss = 0.0
        if data.risk_level in ("high", "critical") and data.monthly_reputation_loss > 0:
            reputation_loss = round(data.monthly_reputation_loss * months * audit_prob, 2)

        path_a_cost = round(expected_penalty + expected_late_fee + reputation_loss, 2)

        # 路径B：一次性整改成本
        path_b_cost = round(data.remediation_cost, 2)

        cost_diff = round(path_a_cost - path_b_cost, 2)

        time_points.append(TimePointResult(
            period=period_key,
            months_elapsed=months,
            path_a_cost=path_a_cost,
            path_b_cost=path_b_cost,
            audit_probability=round(audit_prob, 4),
            expected_penalty=expected_penalty,
            expected_late_fee=expected_late_fee,
            cost_difference=cost_diff,
            total_hidden_tax=total_hidden_tax,
        ))

    # 加载案例引用
    case_refs = _load_case_references(data.industry)

    result = SimulationResult(
        time_points=time_points,
        recommendation="",
        loss_frame_message="",
        case_references=case_refs,
    )
    result.loss_frame_message = _generate_loss_frame(result, data)

    # 推荐建议
    last = time_points[-1]
    if data.monthly_hidden_revenue <= 0:
        result.recommendation = "当前经营模式无明显不合规风险，请继续保持合规经营。"
    elif last.cost_difference > 0:
        result.recommendation = (
            f"强烈建议立即进行合规整改。3年后不合规的期望总成本为 {last.path_a_cost:,.2f} 元，"
            f"而整改成本仅需 {last.path_b_cost:,.2f} 元，节省 {last.cost_difference:,.2f} 元。"
        )
    else:
        result.recommendation = (
            "当前模拟结果显示合规整改成本高于期望风险成本，"
            "但需注意：稽查一旦发生，实际罚款可能远超期望值。建议尽早合规以消除尾部风险。"
        )

    result.technical_summary = {
        "input": {
            "monthly_hidden_revenue": data.monthly_hidden_revenue,
            "comprehensive_tax_rate": data.comprehensive_tax_rate,
            "risk_level": data.risk_level,
            "remediation_cost": data.remediation_cost,
            "monthly_hidden_tax": monthly_tax_hidden,
        },
        "penalty_multiplier": multiplier,
        "audit_probability_matrix_used": AUDIT_PROBABILITY_MATRIX.get(data.risk_level, {}),
        "time_points": [
            {
                "period": tp.period,
                "path_a": tp.path_a_cost,
                "path_b": tp.path_b_cost,
                "diff": tp.cost_difference,
            }
            for tp in time_points
        ],
        "case_references_count": len(case_refs),
    }

    return result


# ═══════════════════════════════════════════════════════════════
# 损失具象化增强模块（Budge 升级）
# ═══════════════════════════════════════════════════════════════

class ThirdPartyConsequence(BaseModel):
    """第三方后果关联"""
    bidding_restriction_days: int = Field(
        ..., ge=0, description="招投标资格预计受限天数"
    )
    bidding_restriction_detail: str = Field(
        ..., description="招投标资格受限详细说明"
    )
    bank_credit_restriction_days: int = Field(
        ..., ge=0, description="银行授信预计受限天数"
    )
    bank_credit_restriction_detail: str = Field(
        ..., description="银行授信受限详细说明"
    )
    government_subsidy_risk: str = Field(
        ..., description="政府补贴/资质风险描述"
    )
    blacklist_risk: str = Field(
        ..., description="税收违法黑名单风险描述"
    )
    social_credit_impact: str = Field(
        ..., description="社会信用影响描述"
    )


class PeerPressure(BaseModel):
    """同行对比压力推送"""
    industry: str = Field(..., description="所属行业")
    peer_cases_count: int = Field(..., ge=0, description="本区同行立案数")
    peer_cases_detail: list[dict] = Field(
        default_factory=list, description="同行立案详情"
    )
    penalty_distribution: dict = Field(
        default_factory=lambda: {"<50万": 0, "50-200万": 0, "200-500万": 0, ">500万": 0},
        description="同行处罚金额分布",
    )
    peer_compliance_rate: float = Field(
        default=0.0, ge=0, le=1, description="同行合规率估算"
    )
    pressure_message: str = Field(
        default="", description="同行对比压力话术"
    )


class OfficialNoticePreview(BaseModel):
    """模拟官方文书预览"""
    document_type: str = Field(default="第三方风险提示", description="文书类型标识")
    document_title: str = Field(..., description="文书标题")
    document_number: str = Field(..., description="模拟文书编号")
    issuing_body: str = Field(default="第三方税务风险分析系统", description="出具方")
    enterprise_name: str = Field(..., description="企业名称")
    credit_code: str = Field(default="", description="统一社会信用代码")
    risk_findings: list[str] = Field(default_factory=list, description="发现的风险点")
    potential_consequences: list[str] = Field(
        default_factory=list, description="潜在后果"
    )
    compliance_deadline: str = Field(default="", description="建议合规整改期限")
    disclaimer: str = Field(
        default="本文件为第三方税务风险分析系统基于公开数据模拟生成，"
                "非税务机关正式文书，仅供参考。",
        description="免责声明",
    )
    full_text: str = Field(default="", description="完整文书文本")


# ── 第三方后果计算 ──

def _compute_third_party_consequences(
    risk_level: str,
    monthly_hidden_revenue: float,
    industry: str,
    revenue_annual: float = 0,
) -> ThirdPartyConsequence:
    """
    基于风险等级和隐匿收入规模，计算第三方后果受限时间。

    逻辑：
      - low/medium → 无立即第三方后果
      - medium_high → 轻度受限（30-90天）
      - high → 中度受限（90-180天）
      - critical → 严重受限（180-365天）
    """
    # 风险→基础受限天数
    base_days_map = {
        "low": 0,
        "medium": 0,
        "medium_high": 30,
        "high": 90,
        "critical": 180,
    }
    base_days = base_days_map.get(risk_level, 0)

    # 根据隐匿收入规模加成
    revenue_bonus = 0
    if monthly_hidden_revenue >= 500_000:
        revenue_bonus = 90
    elif monthly_hidden_revenue >= 200_000:
        revenue_bonus = 45
    elif monthly_hidden_revenue >= 50_000:
        revenue_bonus = 15

    # 招投标资格：金额较大时更容易触发
    bidding_days = min(base_days + revenue_bonus, 365)
    # 银行授信：比招投标稍敏感
    credit_days = min(base_days + int(revenue_bonus * 1.2), 365)

    if risk_level in ("low", "medium"):
        bidding_detail = "当前风险水平下，招投标资格暂不受影响。请保持合规经营以维护企业信用。"
        credit_detail = "当前风险水平下，银行授信暂不受影响。"
        subsidy_risk = "政府补贴资格暂不受影响。"
        blacklist_risk = "当前未被列入税收违法黑名单。"
        social_credit = "社会信用记录良好。"
    elif risk_level == "medium_high":
        bidding_detail = (
            f"若被税务稽查立案，招投标资格预计将在{bidding_days}日内受限。"
            f"根据《招标投标法》及政府采购相关规定，有重大税收违法记录的企业"
            f"将被限制参与政府采购及工程招标。"
        )
        credit_detail = (
            f"若被列入税收违法名单，银行授信额度预计将在{credit_days}日内被压缩"
            f"或冻结，影响企业日常经营资金周转。"
        )
        subsidy_risk = "政府补贴及高新技术企业资质可能面临复核风险。"
        blacklist_risk = (
            "一旦被查实偷税，企业及法定代表人将被列入税收违法黑名单，"
            "公示期3年，期间无法参与政府采购、招投标。"
        )
        social_credit = "企业纳税信用等级可能从A/B级降为C级，影响融资和商业合作。"
    elif risk_level == "high":
        bidding_detail = (
            f"⚠️ 高概率：若被税务稽查立案，招投标资格预计在{bidding_days}日内受限。"
            f"根据《招标投标法》，有重大税收违法记录的企业将被禁止参与政府采购"
            f"及工程招标至少{bidding_days}天。"
        )
        credit_detail = (
            f"⚠️ 高概率：银行授信额度预计将在{credit_days}日内被大幅压缩或取消。"
            f"金融机构会将纳税信用等级作为授信审批的核心参考指标。"
        )
        subsidy_risk = (
            "⚠️ 高新技术企业资质、政府补贴项目、税收优惠政策将面临"
            "取消风险，已享受的优惠可能被追回。"
        )
        blacklist_risk = (
            "⚠️ 查实后将列入税收违法黑名单并公示，法定代表人将被限制"
            "高消费、出境，企业3年内无法参与政府采购。"
        )
        social_credit = (
            "⚠️ 企业纳税信用等级将被直接判为D级，在融资授信、商业投标、"
            "资质审批中面临严重限制。"
        )
    else:  # critical
        bidding_detail = (
            f"🚨 几乎必然：招投标资格将在{bidding_days}日内被取消。"
            f"根据《招标投标法》及《政府采购法》，有严重税收违法记录的企业将被"
            f"永久性限制参与政府采购和工程招标。"
        )
        credit_detail = (
            f"🚨 几乎必然：银行将立即冻结授信额度并启动抽贷程序，"
            f"预计{credit_days}日内完成。已有贷款可能被要求提前清偿。"
        )
        subsidy_risk = (
            "🚨 所有政府补贴、税收优惠政策将被立即取消，已享受的优惠将全数追回。"
            "高新技术企业资质将被撤销。"
        )
        blacklist_risk = (
            "🚨 企业及法定代表人将被列入税收违法黑名单并联合惩戒："
            "限制高消费、限制出境、限制担任企业法定代表人、限制贷款等。"
        )
        social_credit = (
            "🚨 纳税信用等级直接判D级，在信用中国公示，所有合作方将通过"
            "天眼查/企查查等平台看到警示信息，商业信誉严重受损。"
        )

    return ThirdPartyConsequence(
        bidding_restriction_days=bidding_days,
        bidding_restriction_detail=bidding_detail,
        bank_credit_restriction_days=credit_days,
        bank_credit_restriction_detail=credit_detail,
        government_subsidy_risk=subsidy_risk,
        blacklist_risk=blacklist_risk,
        social_credit_impact=social_credit,
    )


# ── 同行对比压力 ──

def _compute_peer_pressure(
    industry: str,
    risk_level: str,
    revenue_annual: float = 0,
) -> PeerPressure:
    """
    动态查询 case_studies.json 中同行业的立案数据和处罚分布，
    生成同行对比压力话术。

    同级匹配：
      - 优先匹配同行业案例
      - 统计处罚金额分布
      - 生成"你们行业已有X家企业被查处"的压力话术
    """
    cases_path = Path(__file__).parent.parent / "data" / "case_studies.json"

    try:
        with open(cases_path, "r", encoding="utf-8") as f:
            cases = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cases = []

    if not isinstance(cases, list):
        cases = []

    # 匹配同行业案例
    peer_cases = [c for c in cases if c.get("industry") == industry]
    if not peer_cases:
        peer_cases = cases  # 无同行匹配时用全量

    # 解析处罚金额分布
    def _parse_penalty_amount(penalty_str: str) -> float:
        """从中文金额描述中提取数值（万元）"""
        import re
        match = re.search(r"约?(\d+)\s*万", str(penalty_str))
        if match:
            return float(match.group(1))
        match = re.search(r"(\d+\.?\d*)\s*万", str(penalty_str))
        if match:
            return float(match.group(1))
        return 0

    penalty_distribution = {"<50万": 0, "50-200万": 0, "200-500万": 0, ">500万": 0}
    for c in peer_cases:
        amount = _parse_penalty_amount(c.get("penalty_amount", ""))
        if amount < 50:
            penalty_distribution["<50万"] += 1
        elif amount < 200:
            penalty_distribution["50-200万"] += 1
        elif amount < 500:
            penalty_distribution["200-500万"] += 1
        else:
            penalty_distribution[">500万"] += 1

    peer_cases_count = len(peer_cases)

    # 同行案例详情（取最近5个）
    peer_cases_detail = []
    for c in peer_cases[:5]:
        peer_cases_detail.append({
            "case_id": c.get("case_id", ""),
            "year": c.get("year", ""),
            "violation": c.get("violation", ""),
            "penalty_amount": c.get("penalty_amount", ""),
            "detection_method": c.get("detection_method", ""),
        })

    # 同行合规率估算（基于立案数据反向推算）
    # 行业案例越多 → 同行合规率越低
    if peer_cases_count >= 8:
        peer_compliance_rate = 0.50
    elif peer_cases_count >= 5:
        peer_compliance_rate = 0.65
    elif peer_cases_count >= 3:
        peer_compliance_rate = 0.75
    else:
        peer_compliance_rate = 0.85

    # 生成压力话术
    total_penalty_count = sum(penalty_distribution.values())
    high_penalty_count = penalty_distribution.get("200-500万", 0) + penalty_distribution.get(">500万", 0)

    if risk_level in ("low", "medium"):
        pressure_message = (
            f"同行业（{industry}）已收录 {peer_cases_count} 起税务稽查案例。"
            f"虽然贵司目前风险较低，但行业内已有警示先例，"
            f"建议保持合规经营的先发优势。"
        )
    elif risk_level == "medium_high":
        pressure_message = (
            f"⚠️ 同行业（{industry}）已收录 {peer_cases_count} 起税务稽查案例，"
            f"其中{high_penalty_count}起处罚金额超过200万元。"
            f"贵司目前处于中高风险区间，行业稽查力度持续加大，"
            f"同行已有{total_penalty_count}家企业被查处，请勿心存侥幸。"
        )
    elif risk_level == "high":
        pressure_message = (
            f"⚠️⚠️ 同行业（{industry}）已收录 {peer_cases_count} 起稽查案例，"
            f"其中{high_penalty_count}起处罚金额超200万元。"
            f"税务局对本行业的关注度持续提升，金税四期上线后稽查覆盖率达历史新高。"
            f"贵司当前风险等级已超过行业内{int(peer_compliance_rate*100)}%的同行，"
            f"请立即启动合规整改。"
        )
    else:  # critical
        pressure_message = (
            f"🚨🚨 同行业（{industry}）已收录 {peer_cases_count} 起稽查案例，"
            f"其中{high_penalty_count}起处罚金额超200万元，最高达千万级。"
            f"本行业已是税务稽查重点关注领域，贵司风险指标显著高于同行均值。"
            f"行业内{int((1-peer_compliance_rate)*100)}%的企业已遭遇稽查处罚，"
            f"贵司被稽查只是时间问题——立即行动，在稽查上门前完成整改！"
        )

    return PeerPressure(
        industry=industry,
        peer_cases_count=peer_cases_count,
        peer_cases_detail=peer_cases_detail,
        penalty_distribution=penalty_distribution,
        peer_compliance_rate=peer_compliance_rate,
        pressure_message=pressure_message,
    )


# ── 模拟官方文书 ──

def _generate_official_notice(
    enterprise_name: str,
    credit_code: str,
    risk_level: str,
    effective_risk_level: str,
    monthly_hidden_revenue: float,
    total_hidden_tax_3year: float,
    audit_probability_1year: float,
    remediation_cost: float,
    third_party: ThirdPartyConsequence,
) -> OfficialNoticePreview:
    """
    生成一份格式仿照《税务事项通知书》的风险提示，
    但明确标注为"第三方风险提示"（非真实税务机关发文）。

    文书结构：
      1. 标题 + 模拟编号
      2. 企业基本信息（名称/信用代码）
      3. 风险事实描述
      4. 法律依据引用
      5. 潜在后果
      6. 合规建议期限
      7. 免责声明
    """
    now = datetime.now()
    doc_date = now.strftime("%Y年%m月%d日")
    doc_number = f"第三方风提〔{now.year}〕第DSF-{now.strftime('%m%d%H%M')}号"

    # 风险事实
    monthly_wan = monthly_hidden_revenue / 10000
    total_tax_wan = total_hidden_tax_3year / 10000

    risk_facts = []
    if monthly_hidden_revenue > 0:
        risk_facts.append(
            f"经第三方风险分析系统扫描，发现贵司存在月均约{monthly_wan:.1f}万元疑似未申报收入，"
            f"对应少缴税款约{monthly_wan * 0.06:.1f}万元/月（按6%综合税率估算）。"
        )
    if effective_risk_level in ("high", "critical"):
        risk_facts.append(
            f"贵司综合风险等级评定为「{_level_name(effective_risk_level)}」，"
            f"在同类企业中处于较高风险区间。"
        )
    if total_hidden_tax_3year > 0:
        risk_facts.append(
            f"按目前模式持续3年，累计少缴税金预计达{total_tax_wan:.1f}万元。"
        )

    if not risk_facts:
        risk_facts.append("本次扫描未发现重大风险敞口。")

    # 法律依据
    legal_basis = [
        "《中华人民共和国税收征收管理法》第三十二条（滞纳金：日万分之五）",
        "《中华人民共和国税收征收管理法》第六十三条（偷税处罚：0.5-5倍罚款）",
        "《纳税信用管理办法（试行）》第二十条（D级纳税人联合惩戒）",
        "《招标投标法》及《政府采购法》（税收违法企业限制参与招投标）",
    ]

    # 潜在后果
    consequences = [
        f"补缴税款本金约{total_tax_wan:.1f}万元",
        f"行政罚款（{_multiplier_name(effective_risk_level)}）",
        f"每日万分之五的滞纳金（复利累积）",
    ]
    if third_party.bidding_restriction_days > 0:
        consequences.append(
            f"招投标资格受限（预计{third_party.bidding_restriction_days}天内）"
        )
    if third_party.bank_credit_restriction_days > 0:
        consequences.append(
            f"银行授信额度压缩或冻结（预计{third_party.bank_credit_restriction_days}天内）"
        )
    consequences.append("纳税信用等级降为D级，社会信用联合惩戒")

    # 合规期限
    if effective_risk_level in ("critical",):
        deadline = "建议立即启动全面合规整改，1个月内完成重点事项"
    elif effective_risk_level in ("high", "medium_high"):
        deadline = "建议在3个月内完成合规整改"
    else:
        deadline = "建议保持警惕，定期自查"

    # 组装全文
    full_text_parts = [
        f"╔══════════════════════════════════════════════════════╗",
        f"║        第三方税务风险提示（模拟文书）                ║",
        f"║        ——非税务机关正式发文，仅供内部参考——          ║",
        f"╚══════════════════════════════════════════════════════╝",
        f"",
        f"文档编号：{doc_number}",
        f"出具日期：{doc_date}",
        f"出具机构：{OfficialNoticePreview.model_fields['issuing_body'].default}",
        f"",
        f"致：{enterprise_name}",
        f"统一社会信用代码：{credit_code or '（未登记）'}",
        f"",
        f"一、风险事实",
        f"",
    ]
    for i, fact in enumerate(risk_facts, 1):
        full_text_parts.append(f"  {i}. {fact}")

    full_text_parts.extend([
        f"",
        f"二、法律依据",
        f"",
    ])
    for basis in legal_basis:
        full_text_parts.append(f"  · {basis}")

    full_text_parts.extend([
        f"",
        f"三、潜在后果",
        f"",
    ])
    for i, cons in enumerate(consequences, 1):
        full_text_parts.append(f"  {i}. {cons}")

    full_text_parts.extend([
        f"",
        f"四、合规整改建议",
        f"",
        f"  {deadline}。当前一次性合规整改成本约{remediation_cost/10000:.1f}万元，"
        f"远低于继续违规的预期代价。",
        f"",
        f"五、重要声明",
        f"",
        f"  本文件由第三方税务风险分析系统基于公开数据和风险模型模拟生成，",
        f"  非税务机关出具的正式《税务事项通知书》。",
        f"  本文件不构成法律意见，具体税务事项请咨询专业税务顾问。",
        f"  建议将此风险提示作为企业内部自查和决策的参考依据。",
    ])

    full_text = "\n".join(full_text_parts)

    # 风险事实摘要用于外部展示
    risk_fact_summary = []
    if monthly_hidden_revenue > 0:
        risk_fact_summary.append(
            f"月均隐匿收入约{monthly_wan:.1f}万元，少缴税款约{monthly_wan * 0.06:.1f}万元/月"
        )
    if total_hidden_tax_3year > 0:
        risk_fact_summary.append(
            f"3年累计少缴税金预计达{total_tax_wan:.1f}万元"
        )
    risk_fact_summary.append(
        f"1年内被稽查概率{audit_probability_1year:.0%}"
    )

    return OfficialNoticePreview(
        document_title=f"第三方税务风险提示——关于{enterprise_name}涉嫌税务违规事项的风险告知",
        document_number=doc_number,
        issuing_body=OfficialNoticePreview.model_fields["issuing_body"].default,
        enterprise_name=enterprise_name,
        credit_code=credit_code,
        risk_findings=risk_fact_summary,
        potential_consequences=consequences,
        compliance_deadline=deadline,
        full_text=full_text,
    )


def _level_name(level: str) -> str:
    """风险等级 → 中文名"""
    return {
        "low": "低风险",
        "medium": "中风险",
        "medium_high": "中高风险",
        "high": "高风险",
        "critical": "严重风险",
    }.get(level, level)


def _multiplier_name(level: str) -> str:
    """风险等级 → 罚款倍数描述"""
    mp = {
        "low": "0.5倍罚款",
        "medium": "1.5倍罚款",
        "medium_high": "2.5倍罚款",
        "high": "3.5倍罚款",
        "critical": "5倍罚款",
    }
    return mp.get(level, "1.5倍罚款")


def run_enhanced_simulation(
    data: SimulationInput,
    enterprise_name: str = "",
    credit_code: str = "",
    revenue_annual: float = 0,
) -> dict:
    """
    运行增强版风险模拟，包含损失具象化（Budge升级）的所有输出。

    返回 dict 包含：
      - simulation: 原始模拟结果
      - third_party_consequences: 第三方后果关联
      - peer_pressure: 同行对比压力
      - official_notice: 模拟官方文书
    """
    # 基础模拟
    sim_result = run_simulation(data)

    # 3年节点数据
    last_tp = sim_result.time_points[-1] if sim_result.time_points else None
    total_hidden_tax_3year = last_tp.total_hidden_tax if last_tp else 0.0
    audit_prob_1year = sim_result.time_points[1].audit_probability if len(sim_result.time_points) > 1 else 0.0

    # 增强模块1：第三方后果
    third_party = _compute_third_party_consequences(
        risk_level=data.risk_level,
        monthly_hidden_revenue=data.monthly_hidden_revenue,
        industry=data.industry,
        revenue_annual=revenue_annual,
    )

    # 增强模块2：同行压力
    peer = _compute_peer_pressure(
        industry=data.industry,
        risk_level=data.risk_level,
        revenue_annual=revenue_annual,
    )

    # 增强模块3：官方文书
    notice = _generate_official_notice(
        enterprise_name=enterprise_name or "目标企业",
        credit_code=credit_code,
        risk_level=data.risk_level,
        effective_risk_level=data.risk_level,
        monthly_hidden_revenue=data.monthly_hidden_revenue,
        total_hidden_tax_3year=total_hidden_tax_3year,
        audit_probability_1year=audit_prob_1year,
        remediation_cost=data.remediation_cost,
        third_party=third_party,
    )

    return {
        "simulation": sim_result,
        "third_party_consequences": third_party.model_dump(),
        "peer_pressure": peer.model_dump(),
        "official_notice": notice.model_dump(),
    }
