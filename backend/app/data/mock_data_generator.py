"""
模拟数据生成器

根据德勤比赛规则——"禁止使用任何真实企业或个人的保密信息"、"作品中所有所涉数据须为
自行构造的模拟数据，或经脱敏处理至无法识别特定主体的数据"——

本模块生成的所有数据均为自行构造的模拟数据，不涉及任何真实企业或个人的保密信息。

五类企业：
  A = 正常企业（杭州明远贸易有限公司）—— 批发零售 · 中型 · 低风险
  B = 轻度风险企业（深圳恒达制造有限公司）—— 制造 · 中型 · 中风险
  C = 重度风险企业（广州鑫盛建筑工程有限公司）—— 建筑 · 大型 · 高风险
  D = 隐匿收入企业（北京云翼科技有限公司）—— 电商 · 大型 · 中高风险
  E = 个体户风险企业（成都蜀味餐饮管理有限公司）—— 餐饮服务 · 小型 · 中风险

产生的数据集：
  - 银行流水（12个月，每月50-80条）
  - 发票数据（12个月，每月20-40张）
  - 纳税申报（4个季度 × 3个税种）
  - 合同台账（20-30份）
  - 财务报表（4个季度 × 3表）
"""

import random
import uuid
import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Any


# ══════════════════════════════════════════════
#  随机种子（保证可复现）
# ══════════════════════════════════════════════
SEED = 42
random.seed(SEED)


# ══════════════════════════════════════════════
#  企业定义
# ══════════════════════════════════════════════

ENTERPRISE_CONFIGS = {
    "A": {
        "name": "杭州明远贸易有限公司",
        "credit_code": "91330100" + "".join(random.choices("0123456789", k=10)),
        "industry": "批发零售",
        "revenue_annual": 32_000_000.0,
        "employee_count": 85,
        "total_assets": 28_000_000.0,
        "annual_profit": 1_800_000.0,
        "tax_rate_industry": 2.5,
        "actual_tax_burden_rate": 2.8,
        "cost_rate_industry": 82.0,
        "actual_cost_rate": 80.0,
        "private_card_ratio": 0.05,
        "is_high_tech": False,
        "is_small_micro": True,
        "risk_level": "low",
        "large_personal_tx_count": 1,
        "input_output_ratio": 0.85,
        "invoice_product_match_rate": 0.85,
        "deviations": {
            "four_flow_match": 0.92,
            "cost_rate": 3.5,
            "tax_burden": 0.3,
        },
        "adjustment_frequency": 1,
        "historical_audits": 0,
        "tax_consulting_per_year": 2,
        "vendors": ["义乌市聚丰供应链管理有限公司", "温州德信电器有限公司", "宁波海纳商贸有限公司", "杭州联华日用品有限公司"],
        "customers": ["浙江百联商超有限公司", "金华永昌贸易有限公司", "绍兴福泰商贸有限公司", "湖州佳品零售有限公司"],
        "products": ["日用百货", "家居用品", "小型家电", "文具办公"],
        "cost_categories": ["商品采购", "仓储物流", "人员工资", "办公费用", "市场推广"],
    },
    "B": {
        "name": "深圳恒达制造有限公司",
        "credit_code": "91440300" + "".join(random.choices("0123456789", k=10)),
        "industry": "制造",
        "revenue_annual": 18_000_000.0,
        "employee_count": 120,
        "total_assets": 32_000_000.0,
        "annual_profit": 950_000.0,
        "tax_rate_industry": 3.5,
        "actual_tax_burden_rate": 2.1,
        "cost_rate_industry": 88.0,
        "actual_cost_rate": 72.0,
        "private_card_ratio": 0.35,
        "is_high_tech": False,
        "is_small_micro": True,
        "risk_level": "medium",
        "large_personal_tx_count": 5,
        "input_output_ratio": 0.55,
        "invoice_product_match_rate": 0.55,
        "deviations": {
            "four_flow_match": 0.72,
            "cost_rate": 13.0,
            "tax_burden": 1.4,
        },
        "adjustment_frequency": 4,
        "historical_audits": 0,
        "tax_consulting_per_year": 0,
        "vendors": ["东莞鑫旺钢材有限公司", "惠州精密五金有限公司", "广州华南塑胶有限公司", "中山电子元器件有限公司"],
        "customers": ["佛山顺德家电有限公司", "东莞电子科技有限公司", "深圳安防设备有限公司"],
        "products": ["电子元器件", "五金配件", "塑胶制品", "精密模具"],
        "cost_categories": ["原材料采购", "人工费用", "设备折旧", "水电动力", "物流费用"],
    },
    "C": {
        "name": "广州鑫盛建筑工程有限公司",
        "credit_code": "91440100" + "".join(random.choices("0123456789", k=10)),
        "industry": "建筑",
        "revenue_annual": 45_000_000.0,
        "employee_count": 65,
        "total_assets": 18_000_000.0,
        "annual_profit": 2_800_000.0,
        "tax_rate_industry": 3.0,
        "actual_tax_burden_rate": 1.2,
        "cost_rate_industry": 92.0,
        "actual_cost_rate": 112.0,
        "private_card_ratio": 0.55,
        "is_high_tech": False,
        "is_small_micro": False,
        "risk_level": "high",
        "large_personal_tx_count": 15,
        "input_output_ratio": 0.25,
        "invoice_product_match_rate": 0.25,
        "deviations": {
            "four_flow_match": 0.45,
            "cost_rate": 27.0,
            "tax_burden": 2.3,
        },
        "adjustment_frequency": 6,
        "historical_audits": 1,
        "tax_consulting_per_year": 0,
        "vendors": ["广州天河建材有限公司", "佛山顺德钢构有限公司", "东莞混凝土供应有限公司", "深圳工程机械设备租赁有限公司"],
        "customers": ["广州越秀地产有限公司", "广东省高速公路建设有限公司", "深圳城市更新有限公司"],
        "products": ["建筑工程", "装修装饰", "市政工程", "土石方工程"],
        "cost_categories": ["材料采购", "人工费", "机械租赁", "分包支出", "招待费用"],
    },
    "D": {
        "name": "北京云翼科技有限公司",
        "credit_code": "91110108" + "".join(random.choices("0123456789", k=10)),
        "industry": "电商",
        "revenue_annual": 150_000_000.0,
        "employee_count": 200,
        "total_assets": 45_000_000.0,
        "annual_profit": 12_000_000.0,
        "tax_rate_industry": 1.8,
        "actual_tax_burden_rate": 0.9,
        "cost_rate_industry": 65.0,
        "actual_cost_rate": 78.0,
        "private_card_ratio": 0.40,
        "is_high_tech": True,
        "is_small_micro": False,
        "risk_level": "medium_high",
        "large_personal_tx_count": 12,
        "input_output_ratio": 0.45,
        "invoice_product_match_rate": 0.40,
        "deviations": {
            "four_flow_match": 0.55,
            "cost_rate": 18.0,
            "tax_burden": 0.9,
        },
        "adjustment_frequency": 5,
        "historical_audits": 0,
        "tax_consulting_per_year": 1,
        "vendors": ["深圳云端服务器租赁有限公司", "杭州云计算服务有限公司", "北京软件开发外包有限公司", "上海数据中心运营有限公司"],
        "customers": ["华为技术有限公司", "阿里巴巴集团", "字节跳动科技有限公司", "美团点评科技有限公司"],
        "products": ["SaaS订阅服务", "技术咨询服务", "软件开发", "系统集成"],
        "cost_categories": ["研发人员工资", "服务器租赁", "市场推广", "技术外包", "办公费用"],
    },
    "E": {
        "name": "成都蜀味餐饮管理有限公司",
        "credit_code": "91510100" + "".join(random.choices("0123456789", k=10)),
        "industry": "餐饮服务",
        "revenue_annual": 6_000_000.0,
        "employee_count": 15,
        "total_assets": 2_500_000.0,
        "annual_profit": 400_000.0,
        "tax_rate_industry": 3.0,
        "actual_tax_burden_rate": 0.6,
        "cost_rate_industry": 85.0,
        "actual_cost_rate": 96.0,
        "private_card_ratio": 0.70,
        "is_high_tech": False,
        "is_small_micro": True,
        "risk_level": "medium",
        "large_personal_tx_count": 8,
        "input_output_ratio": 0.30,
        "invoice_product_match_rate": 0.30,
        "deviations": {
            "four_flow_match": 0.40,
            "cost_rate": 15.0,
            "tax_burden": 2.4,
        },
        "adjustment_frequency": 3,
        "historical_audits": 0,
        "tax_consulting_per_year": 0,
        "vendors": ["成都农产品批发市场有限公司", "四川调味品供应链有限公司", "成都酒水饮料批发有限公司", "成都冷链物流有限公司"],
        "customers": ["散客（堂食）", "美团外卖平台", "饿了么外卖平台", "企业团餐客户"],
        "products": ["中式正餐", "特色小吃", "团餐配送", "私房菜"],
        "cost_categories": ["食材采购", "人工工资", "房租水电", "设备维护", "外卖平台佣金"],
    },
}

# 重新设定seed确保credit_code可重复
random.seed(SEED)
for enterprise_type in ["B", "C", "D", "E"]:
    ENTERPRISE_CONFIGS[enterprise_type]["credit_code"] = {
        "B": "91440300",
        "C": "91440100",
        "D": "91110108",
        "E": "91510100",
    }[enterprise_type] + "".join(random.choices("0123456789", k=10))


# ══════════════════════════════════════════════
#  辅助函数
# ══════════════════════════════════════════════

def _random_amount(mean: float, std: float, min_val: float = 0) -> float:
    """生成正态分布的随机金额"""
    val = random.gauss(mean, std)
    return round(max(min_val, val), 2)


def _generate_invoice_no(month: int, idx: int) -> str:
    """生成发票号码"""
    return f"FP-2025-{month:02d}-{idx:05d}"


def _generate_contract_no(c_type: str, idx: int) -> str:
    """生成合同编号"""
    prefix = "XS" if c_type == "sales" else "CG"
    return f"{prefix}-2025-{idx:04d}"


def _generate_tax_period(quarter: int) -> str:
    """生成纳税期间"""
    return f"2025-Q{quarter}"


def _generate_financial_period(quarter: int) -> str:
    """生成财务报表期间"""
    return f"2025-Q{quarter}"


# ══════════════════════════════════════════════
#  各类数据生成函数
# ══════════════════════════════════════════════

def _generate_bank_transactions(
    config: dict, months: int = 12, min_tx_per_month: int = 50, max_tx_per_month: int = 80,
) -> list[dict[str, Any]]:
    """生成银行流水数据"""
    transactions = []
    annual_revenue = config["revenue_annual"]
    monthly_revenue = annual_revenue / 12
    private_ratio = config["private_card_ratio"]

    large_personal_target = config.get("large_personal_tx_count", 0)

    for month in range(1, months + 1):
        # 本月的公户/私卡交易数
        total_count = random.randint(min_tx_per_month, max_tx_per_month)
        personal_count = max(1, int(total_count * private_ratio))
        corporate_count = total_count - personal_count

        # 公户流水（收入+支出）
        for _ in range(corporate_count):
            is_inflow = random.random() < 0.6  # 60%收入
            direction = "inflow" if is_inflow else "outflow"
            if is_inflow:
                amt = _random_amount(monthly_revenue / corporate_count * 1.5,
                                     monthly_revenue / corporate_count * 0.5, 100)
            else:
                amt = _random_amount(monthly_revenue * 0.3 / corporate_count,
                                     monthly_revenue * 0.1 / corporate_count, 0)

            day = random.randint(1, 28)
            tx_date = date(2025, month, day)

            counterparty_pool = config["customers"] if is_inflow else config["vendors"]
            counterparty = random.choice(counterparty_pool)

            transactions.append({
                "transaction_date": tx_date,
                "amount": amt,
                "direction": direction,
                "account_type": "corporate",
                "account_holder": config["name"],
                "counterparty": counterparty,
                "description": "货款" if is_inflow else "采购款",
                "is_declared": True,
            })

        # 个人卡流水
        for i in range(personal_count):
            is_inflow = random.random() < 0.8  # 私卡多为收入
            direction = "inflow" if is_inflow else "outflow"

            # 控制大额公转私笔数：普通个人卡流出金额控制在50000以下
            amt = _random_amount(20000, 15000, 500) if direction == "outflow" else \
                  _random_amount(monthly_revenue * private_ratio / personal_count * 1.5,
                                 monthly_revenue * private_ratio / personal_count * 0.3, 100)

            day = random.randint(1, 28)
            tx_date = date(2025, month, day)

            counterparty = random.choice(config["customers"] + config["vendors"])

            transactions.append({
                "transaction_date": tx_date,
                "amount": amt,
                "direction": direction,
                "account_type": "personal",
                "account_holder": "法人",
                "counterparty": counterparty,
                "description": "私卡收款" if is_inflow else "个人转账",
                "is_declared": False,
            })

    # 额外插入指定数量的大额公转私交易
    existing_large = sum(
        1 for tx in transactions
        if tx["account_type"] == "personal" and tx["direction"] == "outflow" and tx["amount"] > 50000
    )
    for i in range(max(0, large_personal_target - existing_large)):
        m = random.randint(1, 12)
        day = random.randint(1, 28)
        transactions.append({
            "transaction_date": date(2025, m, day),
            "amount": _random_amount(80000, 30000, 50001),
            "direction": "outflow",
            "account_type": "personal",
            "account_holder": "法人",
            "counterparty": random.choice(config["vendors"]),
            "description": "大额公转私",
            "is_declared": False,
        })

    # 按日期排序
    transactions.sort(key=lambda t: t["transaction_date"])
    return transactions


def _generate_invoices(config: dict, months: int = 12,
                       min_per_month: int = 20, max_per_month: int = 40) -> list[dict[str, Any]]:
    """生成发票数据"""
    invoices = []
    annual_revenue = config["revenue_annual"]
    monthly_revenue = annual_revenue / 12
    input_output_ratio = config.get("input_output_ratio", 0.8)
    match_rate = config.get("invoice_product_match_rate", 0.8)
    # 建筑行业增值税率9%，其他行业13%
    vat_rate = 0.09 if config["industry"] == "建筑" else 0.13

    for month in range(1, months + 1):
        total_count = random.randint(min_per_month, max_per_month)
        output_count = max(5, int(total_count * 0.6))
        input_count = total_count - output_count

        # 销项发票
        for idx in range(output_count):
            amt = _random_amount(monthly_revenue / output_count, monthly_revenue * 0.3 / output_count, 100)
            tax = round(amt * vat_rate, 2)
            # 品名匹配率：按 match_rate 概率选择匹配品名
            if random.random() < match_rate:
                product = random.choice(config["products"])
            else:
                product = random.choice(["其他商品", "杂项", "办公耗材", "服务费", "咨询费"])

            invoices.append({
                "invoice_no": _generate_invoice_no(month, idx + 1),
                "invoice_type": "output",
                "invoice_date": date(2025, month, random.randint(1, 28)),
                "product_name": product,
                "tax_rate": round(vat_rate * 100, 0),
                "amount": round(amt / (1 + vat_rate), 2),
                "tax_amount": tax,
                "total_amount": amt,
                "buyer_name": random.choice(config["customers"]),
                "seller_name": config["name"],
                "is_digital": random.random() < 0.5,
            })

        # 进项发票（数量为 销项 × input_output_ratio 左右的波动）
        for idx in range(input_count):
            amt = _random_amount(monthly_revenue * input_output_ratio / input_count,
                                 monthly_revenue * 0.2 / input_count, 100)
            tax = round(amt * vat_rate, 2)
            if random.random() < match_rate:
                product = random.choice(config["products"])
            else:
                product = random.choice(["其他商品", "杂项", "办公耗材", "服务费", "咨询费"])

            invoices.append({
                "invoice_no": _generate_invoice_no(month, idx + output_count + 1),
                "invoice_type": "input",
                "invoice_date": date(2025, month, random.randint(1, 28)),
                "product_name": product,
                "tax_rate": round(vat_rate * 100, 0),
                "amount": round(amt / (1 + vat_rate), 2),
                "tax_amount": tax,
                "total_amount": amt,
                "buyer_name": config["name"],
                "seller_name": random.choice(config["vendors"]),
                "is_digital": random.random() < 0.5,
            })

    invoices.sort(key=lambda inv: inv["invoice_date"])
    return invoices


def _generate_tax_declarations(config: dict, quarters: int = 4) -> list[dict[str, Any]]:
    """生成纳税申报记录。税额从 actual_tax_burden_rate 推导，确保年度税负率与配置一致。"""
    declarations = []
    annual_revenue = config["revenue_annual"]
    tax_burden_actual = config["actual_tax_burden_rate"]
    private_ratio = config["private_card_ratio"]

    # 目标年纳税总额 = 年营收 × 实际税负率
    target_annual_tax = annual_revenue * tax_burden_actual / 100.0

    for quarter in range(1, quarters + 1):
        seasonal_factor = [0.22, 0.25, 0.23, 0.30][quarter - 1]
        q_revenue = annual_revenue * seasonal_factor
        # 申报收入（C企业隐匿更多）
        hide_ratio = private_ratio * random.uniform(0.8, 1.2)
        declared_revenue = q_revenue * (1 - hide_ratio)

        period = _generate_tax_period(quarter)
        # 季度目标税额（从年目标按季节比例分配）
        q_target_tax = target_annual_tax * seasonal_factor

        # 增值税 — 约占总税负的55%
        vat_amount = round(q_target_tax * 0.55 * random.uniform(0.92, 1.08), 2)
        declarations.append({
            "tax_type": "vat",
            "period": f"{period}-VAT",
            "declared_revenue": round(declared_revenue, 2),
            "declared_tax": vat_amount,
            "actual_paid": round(vat_amount * random.uniform(0.95, 1.0), 2),
            "declaration_date": date(2025, quarter * 3, random.randint(10, 15)),
        })

        # 企业所得税 — 约占总税负的35%
        it_amount = round(q_target_tax * 0.35 * random.uniform(0.92, 1.08), 2)
        declarations.append({
            "tax_type": "income_tax",
            "period": f"{period}-IT",
            "declared_revenue": round(declared_revenue, 2),
            "declared_tax": it_amount,
            "actual_paid": round(it_amount * random.uniform(0.95, 1.0), 2),
            "declaration_date": date(2025, quarter * 3, random.randint(10, 15)),
        })

        # 个人所得税 — 约占总税负的10%
        pax_amount = round(q_target_tax * 0.10 * random.uniform(0.92, 1.08), 2)
        declarations.append({
            "tax_type": "personal_income_tax",
            "period": f"{period}-PAX",
            "declared_revenue": 0.0,
            "declared_tax": pax_amount,
            "actual_paid": round(pax_amount * random.uniform(0.95, 1.0), 2),
            "declaration_date": date(2025, quarter * 3, random.randint(10, 15)),
        })

    return declarations


def _generate_contracts(config: dict, min_count: int = 20, max_count: int = 30) -> list[dict[str, Any]]:
    """生成合同台账"""
    contracts = []
    total_count = random.randint(min_count, max_count)
    annual_revenue = config["revenue_annual"]
    avg_contract = annual_revenue / (total_count * 0.6)  # 60%为销售合同

    for idx in range(1, total_count + 1):
        is_sales = idx <= int(total_count * 0.6)
        c_type = "sales" if is_sales else "purchase"
        counterparty = random.choice(config["customers"] if is_sales else config["vendors"])
        amount = _random_amount(avg_contract, avg_contract * 0.4, 5000)

        signing_month = random.randint(1, 12)
        signing_day = random.randint(1, 28)

        status_weights = [0.6, 0.25, 0.15] if config.get("risk_level") != "high" else [0.3, 0.2, 0.5]
        status = random.choices(
            ["履约完成", "履行中", "终止/争议"],
            weights=status_weights,
            k=1,
        )[0]

        contracts.append({
            "contract_no": _generate_contract_no(c_type, idx),
            "contract_type": c_type,
            "counterparty": counterparty,
            "contract_amount": amount,
            "signing_date": date(2025, signing_month, signing_day),
            "execution_status": status,
        })

    contracts.sort(key=lambda c: c["signing_date"])
    return contracts


def _generate_financial_statements(config: dict, quarters: int = 4) -> list[dict[str, Any]]:
    """生成财务报表"""
    statements = []
    annual_revenue = config["revenue_annual"]
    total_assets = config["total_assets"]
    actual_cost_rate = config["actual_cost_rate"]
    actual_tax_burden = config["actual_tax_burden_rate"]

    for quarter in range(1, quarters + 1):
        seasonal_factor = [0.22, 0.25, 0.23, 0.30][quarter - 1]
        seasonal_factor += random.uniform(-0.03, 0.03)
        q_revenue = annual_revenue * seasonal_factor
        q_cost = q_revenue * actual_cost_rate / 100.0
        q_profit = q_revenue - q_cost

        period = _generate_financial_period(quarter)

        # 资产负债率：根据风险等级设定
        # A=低风险: 资产负债率≈0.50, B=中风险: ≈0.65, C=高风险: ≈0.80
        liab_ratio_map = {"low": 0.50, "medium": 0.65, "high": 0.80}
        liab_ratio = liab_ratio_map.get(config.get("risk_level", "low"), 0.50)
        q_assets = round(total_assets * seasonal_factor * 4, 2)
        q_liabilities = round(q_assets * liab_ratio, 2)

        # 资产负债表
        statements.append({
            "period": f"{period}-BS",
            "statement_type": "balance_sheet",
            "total_assets": q_assets,
            "total_liabilities": q_liabilities,
            "total_revenue": round(q_revenue, 2),
            "total_cost": round(q_cost, 2),
            "net_profit": round(q_profit, 2),
            "operating_cash_flow": round(q_revenue * 0.8, 2),
            "tax_burden_rate": actual_tax_burden,
            "cost_rate": actual_cost_rate,
        })

        # 利润表
        statements.append({
            "period": f"{period}-PL",
            "statement_type": "income_statement",
            "total_assets": 0.0,
            "total_liabilities": 0.0,
            "total_revenue": round(q_revenue, 2),
            "total_cost": round(q_cost, 2),
            "net_profit": round(q_profit, 2),
            "operating_cash_flow": 0.0,
            "tax_burden_rate": actual_tax_burden,
            "cost_rate": actual_cost_rate,
        })

        # 现金流量表
        statements.append({
            "period": f"{period}-CF",
            "statement_type": "cash_flow",
            "total_assets": 0.0,
            "total_liabilities": 0.0,
            "total_revenue": round(q_revenue, 2),
            "total_cost": round(q_cost, 2),
            "net_profit": 0.0,
            "operating_cash_flow": round(q_revenue * 0.75, 2),
            "tax_burden_rate": actual_tax_burden,
            "cost_rate": actual_cost_rate,
        })

    return statements


# ══════════════════════════════════════════════
#  主函数
# ══════════════════════════════════════════════

def generate_mock_data(enterprise_type: Literal["A", "B", "C", "D", "E"]) -> dict:
    """
    生成指定类型企业的完整模拟数据集。

    Args:
        enterprise_type: 企业类型 A/B/C/D/E

    Returns:
        dict: 包含企业信息、银行流水、发票、申报、合同、财务报表的完整数据集

    Raises:
        ValueError: 企业类型无效时抛出
    """
    if enterprise_type not in ENTERPRISE_CONFIGS:
        raise ValueError(
            f"无效的企业类型: '{enterprise_type}'，有效值为 'A', 'B', 'C', 'D', 'E'"
        )

    random.seed(SEED + ord(enterprise_type))

    config = ENTERPRISE_CONFIGS[enterprise_type]

    bank_transactions = _generate_bank_transactions(config)
    invoices = _generate_invoices(config)
    tax_declarations = _generate_tax_declarations(config)
    contracts = _generate_contracts(config)
    financial_statements = _generate_financial_statements(config)

    return {
        "enterprise_info": {
            "name": config["name"],
            "credit_code": config["credit_code"],
            "industry": config["industry"],
            "revenue_annual": config["revenue_annual"],
            "employee_count": config["employee_count"],
            "total_assets": config["total_assets"],
            "annual_profit": config["annual_profit"],
            "tax_rate_industry": config["tax_rate_industry"],
            "actual_tax_burden_rate": config["actual_tax_burden_rate"],
            "cost_rate_industry": config["cost_rate_industry"],
            "actual_cost_rate": config["actual_cost_rate"],
            "private_card_ratio": config["private_card_ratio"],
            "is_high_tech": config["is_high_tech"],
            "is_small_micro": config["is_small_micro"],
            "risk_level": config["risk_level"],
            "enterprise_type": enterprise_type,
        },
        "bank_transactions": bank_transactions,
        "invoices": invoices,
        "tax_declarations": tax_declarations,
        "contracts": contracts,
        "financial_statements": financial_statements,
        "_meta": {
            "generated_at": date.today().isoformat(),
            "enterprise_type": enterprise_type,
            "bank_transactions_count": len(bank_transactions),
            "invoices_count": len(invoices),
            "tax_declarations_count": len(tax_declarations),
            "contracts_count": len(contracts),
            "financial_statements_count": len(financial_statements),
            "disclaimer": "本数据为自行构造的模拟数据，已脱敏处理，不包含任何真实企业或个人保密信息。",
        },
    }


async def load_mock_data_to_db(
    enterprise_type: Literal["A", "B", "C", "D", "E"],
    db_session,
    existing_enterprise_id: str | None = None,
) -> str:
    """
    将模拟数据批量加载到数据库。

    Args:
        enterprise_type: 企业类型 A/B/C/D/E
        db_session: SQLAlchemy 异步数据库会话
        existing_enterprise_id: 已存在的企业ID，若提供则关联到该企业（仅加载子表数据）

    Returns:
        str: 企业ID（新建或已存在的）

    Note:
        此函数需要数据库连接可用。
    """
    from app.models.enterprise import Enterprise, IndustryType, RiskLevelEnhanced
    from app.models.bank_transaction import BankTransaction, DirectionType, AccountType
    from app.models.invoice import Invoice, InvoiceType
    from app.models.tax_declaration import TaxDeclaration, TaxType
    from app.models.contract import Contract, ContractType
    from app.models.financial_statement import FinancialStatement, StatementType

    data = generate_mock_data(enterprise_type)
    info = data["enterprise_info"]

    industry_map = {
        "批发零售": IndustryType.WHOLESALE_RETAIL,
        "制造": IndustryType.MANUFACTURING,
        "建筑": IndustryType.CONSTRUCTION,
        "电商": IndustryType.E_COMMERCE,
        "餐饮服务": IndustryType.CATERING,
    }
    risk_map = {
        "low": RiskLevelEnhanced.LOW,
        "medium": RiskLevelEnhanced.MEDIUM,
        "medium_high": RiskLevelEnhanced.MEDIUM_HIGH,
        "high": RiskLevelEnhanced.HIGH,
        "critical": RiskLevelEnhanced.CRITICAL,
    }

    if existing_enterprise_id:
        enterprise_id = existing_enterprise_id
    else:
        enterprise_id = str(uuid.uuid4())
        enterprise = Enterprise(
            id=enterprise_id,
            name=info["name"],
            credit_code=info["credit_code"],
            industry=industry_map.get(info["industry"], IndustryType.WHOLESALE_RETAIL),
            revenue_annual=info["revenue_annual"],
            employee_count=info["employee_count"],
            tax_rate_claimed=info["tax_rate_industry"],
            cost_rate_claimed=info["cost_rate_industry"],
            is_high_tech=info["is_high_tech"],
            is_small_micro=info["is_small_micro"],
            risk_level=risk_map.get(info["risk_level"], RiskLevelEnhanced.LOW),
        )
        db_session.add(enterprise)
        await db_session.flush()

    # ── 银行流水（批量插入）──
    batch_txs = [
        BankTransaction(
            enterprise_id=enterprise_id,
            transaction_date=tx["transaction_date"],
            amount=tx["amount"],
            direction=DirectionType.INFLOW if tx["direction"] == "inflow" else DirectionType.OUTFLOW,
            account_type=AccountType.CORPORATE if tx["account_type"] == "corporate" else AccountType.PERSONAL,
            account_holder=tx["account_holder"],
            counterparty=tx["counterparty"],
            description=tx["description"],
            is_declared=tx["is_declared"],
        )
        for tx in data["bank_transactions"]
    ]
    db_session.add_all(batch_txs)

    # ── 发票（批量插入）──
    batch_invs = [
        Invoice(
            enterprise_id=enterprise_id,
            invoice_no=inv["invoice_no"],
            invoice_type=InvoiceType.OUTPUT if inv["invoice_type"] == "output" else InvoiceType.INPUT,
            invoice_date=inv["invoice_date"],
            amount=inv["amount"],
            tax_amount=inv["tax_amount"],
            total_amount=inv["total_amount"],
            product_name=inv["product_name"],
            buyer_name=inv["buyer_name"],
            seller_name=inv["seller_name"],
            is_digital=inv["is_digital"],
        )
        for inv in data["invoices"]
    ]
    db_session.add_all(batch_invs)

    # ── 纳税申报（批量插入）──
    tax_type_map = {
        "vat": TaxType.VAT,
        "income_tax": TaxType.INCOME_TAX,
        "personal_income_tax": TaxType.PERSONAL_INCOME_TAX,
    }
    batch_decls = [
        TaxDeclaration(
            enterprise_id=enterprise_id,
            tax_type=tax_type_map[decl["tax_type"]],
            period=decl["period"],
            declared_revenue=decl["declared_revenue"],
            declared_tax=decl["declared_tax"],
            actual_paid=decl["actual_paid"],
            declaration_date=decl["declaration_date"],
        )
        for decl in data["tax_declarations"]
    ]
    db_session.add_all(batch_decls)

    # ── 合同（批量插入）──
    batch_cts = [
        Contract(
            enterprise_id=enterprise_id,
            contract_no=ct["contract_no"],
            contract_type=ContractType.SALES if ct["contract_type"] == "sales" else ContractType.PURCHASE,
            counterparty=ct["counterparty"],
            contract_amount=ct["contract_amount"],
            signing_date=ct["signing_date"],
            execution_status=ct["execution_status"],
        )
        for ct in data["contracts"]
    ]
    db_session.add_all(batch_cts)

    # ── 财务报表（批量插入）──
    stmt_type_map = {
        "balance_sheet": StatementType.BALANCE_SHEET,
        "income_statement": StatementType.INCOME_STATEMENT,
        "cash_flow": StatementType.CASH_FLOW,
    }
    batch_stmts = [
        FinancialStatement(
            enterprise_id=enterprise_id,
            period=stmt["period"],
            statement_type=stmt_type_map[stmt["statement_type"]],
            total_assets=stmt["total_assets"],
            total_liabilities=stmt.get("total_liabilities", 0.0),
            total_revenue=stmt["total_revenue"],
            total_cost=stmt["total_cost"],
            net_profit=stmt["net_profit"],
            operating_cash_flow=stmt["operating_cash_flow"],
            tax_burden_rate=stmt["tax_burden_rate"],
            cost_rate=stmt["cost_rate"],
        )
        for stmt in data["financial_statements"]
    ]
    db_session.add_all(batch_stmts)

    await db_session.flush()
    return str(enterprise_id)


# ══════════════════════════════════════════════
#  便捷函数
# ══════════════════════════════════════════════

def get_enterprise_summary(enterprise_type: Literal["A", "B", "C", "D", "E"]) -> dict:
    """
    获取企业摘要信息（仅基本信息，不生成全部数据）。

    Args:
        enterprise_type: 企业类型

    Returns:
        dict: 企业摘要
    """
    config = ENTERPRISE_CONFIGS.get(enterprise_type)
    if not config:
        raise ValueError(f"无效的企业类型: '{enterprise_type}'")
    return dict(config)


__all__ = [
    "generate_mock_data",
    "load_mock_data_to_db",
    "get_enterprise_summary",
    "ENTERPRISE_CONFIGS",
]
