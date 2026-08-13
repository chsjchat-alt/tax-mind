"""
财务数据全面生成与导入脚本 — 2025年6月（单月完整经营周期）
============================================================
生成内容：
  1. 全量月度会计凭证（双分录，借贷平衡）
  2. 审计TB（试算平衡表）+ 审计调整分录 + 重分类分录
  3. 月度财务决算审计报告
  4. 资产负债表 + 利润表 + 现金流量表（勾稽关系成立）
  5. 税务台账（增值税、企业所得税、印花税等）
============================================================
数据来源：基于国家统计局行业统计年鉴、国家税务总局行业税负预警值、
         行业协会公开报告综合分析得出的脱敏行业均值参数。
         所有数据均为自行构造的模拟数据，不涉及任何真实企业信息。
============================================================
"""

import argparse
import asyncio
import json
import random
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SEED = 42
random.seed(SEED)

REPORT_MONTH = 6
REPORT_YEAR = 2025
REPORT_MONTH_LABEL = "2025-06"
DAYS_IN_MONTH = 30


INDUSTRY_PARAMS: dict[str, dict] = {
    "A": {
        "name": "杭州明远贸易有限公司", "industry": "批发零售",
        "annual_revenue": 32_000_000.0, "annual_profit": 1_800_000.0,
        "total_assets": 28_000_000.0, "employee_count": 85,
        "monthly_revenue": 2_933_000.0, "gross_margin": 0.15, "net_margin": 0.032,
        "vat_rate": 0.13, "income_tax_rate": 0.05,
        "cost_structure": {"商品采购成本": 0.82, "仓储物流费": 0.03, "人员工资": 0.045,
            "市场推广费": 0.012, "办公及管理费": 0.02, "财务费用": 0.008, "折旧摊销": 0.015},
        "current_asset_ratio": 0.75, "fixed_asset_ratio": 0.18, "other_asset_ratio": 0.07,
        "current_liability_ratio": 0.85, "long_term_debt_ratio": 0.10,
        "ar_days": 45, "inventory_days": 60, "ap_days": 50,
        "fixed_assets": 5_040_000, "accum_depreciation": 1_680_000,
        "monthly_depreciation": 25_000,
        "employees": {"销售": 35, "仓储物流": 15, "行政财务": 12, "管理": 8, "采购": 15},
        "avg_salary": 12_000,
        "vendors": ["义乌市聚丰供应链管理有限公司", "温州德信电器有限公司", "宁波海纳商贸有限公司", "杭州联华日用品有限公司"],
        "customers": ["浙江百联商超有限公司", "金华永昌贸易有限公司", "绍兴福泰商贸有限公司", "湖州佳品零售有限公司"],
    },
    "B": {
        "name": "深圳恒达制造有限公司", "industry": "制造",
        "annual_revenue": 18_000_000.0, "annual_profit": 950_000.0,
        "total_assets": 32_000_000.0, "employee_count": 120,
        "monthly_revenue": 1_530_000.0, "gross_margin": 0.25, "net_margin": 0.065,
        "vat_rate": 0.13, "income_tax_rate": 0.05,
        "cost_structure": {"原材料成本": 0.60, "直接人工": 0.12, "制造费用（折旧）": 0.065,
            "水电动力": 0.035, "物流运输": 0.02, "管理费用": 0.04, "销售费用": 0.015, "财务费用": 0.01},
        "current_asset_ratio": 0.54, "fixed_asset_ratio": 0.39, "other_asset_ratio": 0.07,
        "current_liability_ratio": 0.62, "long_term_debt_ratio": 0.28,
        "ar_days": 75, "inventory_days": 85, "ap_days": 60,
        "fixed_assets": 12_480_000, "accum_depreciation": 4_160_000,
        "monthly_depreciation": 98_000,
        "employees": {"生产工人": 80, "技术研发": 12, "质检": 8, "行政财务": 10, "管理": 10},
        "avg_salary": 10_500,
        "vendors": ["东莞鑫旺钢材有限公司", "惠州精密五金有限公司", "广州华南塑胶有限公司", "中山电子元器件有限公司"],
        "customers": ["佛山顺德家电有限公司", "东莞电子科技有限公司", "深圳安防设备有限公司"],
    },
    "C": {
        "name": "广州鑫盛建筑工程有限公司", "industry": "建筑",
        "annual_revenue": 45_000_000.0, "annual_profit": 2_800_000.0,
        "total_assets": 18_000_000.0, "employee_count": 65,
        "monthly_revenue": 4_275_000.0, "gross_margin": 0.11, "net_margin": 0.045,
        "vat_rate": 0.09, "income_tax_rate": 0.25,
        "cost_structure": {"材料采购": 0.44, "分包支出": 0.26, "人工费": 0.12, "机械租赁": 0.065,
            "业务招待费": 0.025, "管理费用": 0.03},
        "current_asset_ratio": 0.70, "fixed_asset_ratio": 0.24, "other_asset_ratio": 0.06,
        "current_liability_ratio": 0.80, "long_term_debt_ratio": 0.12,
        "ar_days": 150, "inventory_days": 120, "ap_days": 120,
        "fixed_assets": 4_320_000, "accum_depreciation": 1_440_000,
        "monthly_depreciation": 36_000,
        "employees": {"项目管理人员": 25, "施工技术人员": 20, "行政财务": 8, "管理": 12},
        "avg_salary": 15_000,
        "vendors": ["广州天河建材有限公司", "佛山顺德钢构有限公司", "东莞混凝土供应有限公司", "深圳工程机械设备租赁有限公司"],
        "customers": ["广州越秀地产有限公司", "广东省高速公路建设有限公司", "深圳城市更新有限公司"],
    },
    "D": {
        "name": "北京云翼科技有限公司", "industry": "电商",
        "annual_revenue": 150_000_000.0, "annual_profit": 12_000_000.0,
        "total_assets": 45_000_000.0, "employee_count": 200,
        "monthly_revenue": 13_500_000.0, "gross_margin": 0.45, "net_margin": 0.10,
        "vat_rate": 0.06, "income_tax_rate": 0.15,
        "cost_structure": {"服务器及带宽": 0.065, "研发人员工资": 0.24, "技术外包": 0.075,
            "市场推广费": 0.10, "销售佣金": 0.04, "管理费用": 0.05, "办公费用": 0.03, "折旧摊销": 0.015},
        "current_asset_ratio": 0.75, "fixed_asset_ratio": 0.10, "other_asset_ratio": 0.15,
        "current_liability_ratio": 0.75, "long_term_debt_ratio": 0.12,
        "ar_days": 55, "inventory_days": 0, "ap_days": 40,
        "fixed_assets": 4_500_000, "accum_depreciation": 2_250_000,
        "monthly_depreciation": 45_000,
        "employees": {"研发": 110, "销售": 35, "市场": 20, "行政财务": 18, "管理": 17},
        "avg_salary": 22_000,
        "vendors": ["深圳云端服务器租赁有限公司", "杭州云计算服务有限公司", "北京软件开发外包有限公司"],
        "customers": ["华为技术有限公司", "阿里巴巴集团", "字节跳动科技有限公司", "美团点评科技有限公司"],
    },
    "E": {
        "name": "成都蜀味餐饮管理有限公司", "industry": "餐饮服务",
        "annual_revenue": 6_000_000.0, "annual_profit": 400_000.0,
        "total_assets": 2_500_000.0, "employee_count": 25,
        "monthly_revenue": 540_000.0, "gross_margin": 0.58, "net_margin": 0.08,
        "vat_rate": 0.01, "income_tax_rate": 0.05,
        "cost_structure": {"食材成本": 0.40, "人工工资": 0.25, "房租水电": 0.12,
            "外卖平台佣金": 0.065, "设备维护": 0.02, "其他费用": 0.03, "折旧摊销": 0.05},
        "current_asset_ratio": 0.52, "fixed_asset_ratio": 0.40, "other_asset_ratio": 0.08,
        "current_liability_ratio": 0.86, "long_term_debt_ratio": 0.06,
        "ar_days": 10, "inventory_days": 10, "ap_days": 35,
        "fixed_assets": 1_000_000, "accum_depreciation": 400_000,
        "monthly_depreciation": 18_000,
        "employees": {"厨师": 8, "服务员": 10, "管理": 4, "采购后勤": 3},
        "avg_salary": 7_500,
        "vendors": ["成都农产品批发市场有限公司", "四川调味品供应链有限公司", "成都酒水饮料批发有限公司"],
        "customers": ["散客（堂食）", "美团外卖平台", "饿了么外卖平台", "企业团餐客户"],
    },
}

CHART_OF_ACCOUNTS = {
    "1001": "库存现金", "1002": "银行存款", "1012": "其他货币资金",
    "1122": "应收账款", "1123": "预付账款", "1221": "其他应收款",
    "1403": "原材料", "1405": "库存商品", "1406": "发出商品",
    "1601": "固定资产", "1602": "累计折旧", "1701": "无形资产", "1801": "长期待摊费用",
    "2001": "短期借款", "2202": "应付账款", "2203": "预收账款",
    "2211": "应付职工薪酬", "2221": "应交税费",
    "222101": "应交增值税", "222102": "应交企业所得税",
    "222103": "应交城市维护建设税", "222104": "应交教育费附加",
    "222105": "应交地方教育附加", "222106": "应交印花税",
    "2241": "其他应付款", "2501": "长期借款",
    "4001": "实收资本", "4002": "资本公积", "4101": "盈余公积",
    "4103": "本年利润", "4104": "利润分配",
    "6001": "主营业务收入", "6401": "主营业务成本",
    "6403": "税金及附加", "6601": "销售费用", "6602": "管理费用",
    "6603": "财务费用", "6711": "营业外支出", "6801": "所得税费用",
}


def _amt(mean: float, std: float, min_val: float = 0) -> float:
    return round(max(min_val, random.gauss(mean, std)), 2)


def _d(value: float) -> Decimal:
    return Decimal(str(round(value, 2))).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _month_day(day: int) -> date:
    return date(REPORT_YEAR, REPORT_MONTH, min(day, DAYS_IN_MONTH))


def _voucher_no(seq: int) -> str:
    return f"记-{REPORT_YEAR}-{REPORT_MONTH:02d}-{seq:03d}"


def generate_monthly_vouchers(et: str, p: dict) -> list[dict]:
    vouchers: list[dict] = []
    seq = 0
    monthly = p["monthly_revenue"]
    gross_margin = p["gross_margin"]
    vat_rate = p["vat_rate"]
    employees = p["employees"]
    avg_salary = p["avg_salary"]
    vendors = p["vendors"]
    customers = p["customers"]
    total_employees = sum(employees.values())
    monthly_payroll = total_employees * avg_salary
    monthly_rev_ex_tax = monthly
    monthly_output_vat = round(monthly_rev_ex_tax * vat_rate, 2)
    monthly_cogs = round(monthly_rev_ex_tax * (1 - gross_margin), 2)

    def add_voucher(vtype: str, desc: str, entries: list[dict]):
        nonlocal seq
        seq += 1
        td = sum(e["amount"] for e in entries if e["direction"] == "debit")
        tc = sum(e["amount"] for e in entries if e["direction"] == "credit")
        assert abs(td - tc) < 0.02, f"借贷不平！借={td}, 贷={tc}"
        vouchers.append({"voucher_no": _voucher_no(seq), "voucher_date": _month_day(random.randint(1, DAYS_IN_MONTH)),
                          "voucher_type": vtype, "description": desc,
                          "attachment_count": random.randint(1, 8), "entries": entries, "is_posted": True})

    num_receipts = random.randint(8, min(18, len(customers) * 4))
    remaining_rev = monthly_rev_ex_tax
    for i in range(num_receipts):
        portion = remaining_rev / (num_receipts - i) * random.uniform(0.7, 1.3)
        portion = min(portion, remaining_rev)
        portion_rev = round(portion, 2)
        portion_vat = round(portion_rev * vat_rate, 2)
        total = round(portion_rev + portion_vat, 2)
        customer = random.choice(customers)
        add_voucher("receipt", f"销售商品给{customer}", [
            {"direction": "debit", "account_code": "1002", "account_name": "银行存款", "amount": total},
            {"direction": "credit", "account_code": "6001", "account_name": "主营业务收入", "amount": portion_rev,
             "auxiliary": {"customer": customer}},
            {"direction": "credit", "account_code": "222101", "account_name": "应交增值税", "amount": portion_vat},
        ])
        if random.random() < 0.35:
            ar_amt = round(portion_rev * random.uniform(0.2, 0.5), 2)
            ar_vat = round(ar_amt * vat_rate, 2)
            ar_total = round(ar_amt + ar_vat, 2)
            add_voucher("transfer", f"确认对{customer}的应收账款", [
                {"direction": "debit", "account_code": "1122", "account_name": "应收账款", "amount": ar_total},
                {"direction": "credit", "account_code": "6001", "account_name": "主营业务收入", "amount": ar_amt},
                {"direction": "credit", "account_code": "222101", "account_name": "应交增值税", "amount": ar_vat},
            ])
        remaining_rev = max(0, round(remaining_rev - portion_rev, 2))

    num_purchases = random.randint(10, 20)
    for _ in range(num_purchases):
        vendor = random.choice(vendors)
        purchase_amt = _amt(monthly_cogs / num_purchases, monthly_cogs * 0.15 / num_purchases, 1000)
        input_vat = round(purchase_amt * vat_rate, 2)
        total_pay = round(purchase_amt + input_vat, 2)
        add_voucher("payment", f"向{vendor}采购货物", [
            {"direction": "debit", "account_code": "1405", "account_name": "库存商品", "amount": purchase_amt},
            {"direction": "debit", "account_code": "222101", "account_name": "应交增值税", "amount": input_vat},
            {"direction": "credit", "account_code": "1002", "account_name": "银行存款", "amount": total_pay},
        ])

    add_voucher("transfer", "结转本月销售成本", [
        {"direction": "debit", "account_code": "6401", "account_name": "主营业务成本", "amount": monthly_cogs},
        {"direction": "credit", "account_code": "1405", "account_name": "库存商品", "amount": monthly_cogs},
    ])

    if "生产工人" in employees:
        prod_cost = employees["生产工人"] * avg_salary
        add_voucher("transfer", "计提生产工人工资", [
            {"direction": "debit", "account_code": "6401", "account_name": "主营业务成本", "amount": prod_cost},
            {"direction": "credit", "account_code": "2211", "account_name": "应付职工薪酬", "amount": prod_cost},
        ])

    admin_emp = employees.get("行政财务", 0) + employees.get("管理", 0)
    sales_emp = employees.get("销售", 0) + employees.get("市场", 0)
    mgmt_payroll = admin_emp * avg_salary
    sales_payroll = sales_emp * avg_salary
    if mgmt_payroll > 0:
        add_voucher("transfer", "计提行政管理人员工资", [
            {"direction": "debit", "account_code": "6602", "account_name": "管理费用", "amount": mgmt_payroll},
            {"direction": "credit", "account_code": "2211", "account_name": "应付职工薪酬", "amount": mgmt_payroll},
        ])
    if sales_payroll > 0:
        add_voucher("transfer", "计提销售人员工资", [
            {"direction": "debit", "account_code": "6601", "account_name": "销售费用", "amount": sales_payroll},
            {"direction": "credit", "account_code": "2211", "account_name": "应付职工薪酬", "amount": sales_payroll},
        ])

    net_payroll = round(monthly_payroll * 0.82, 2)
    itax = round(monthly_payroll - net_payroll, 2)
    add_voucher("payment", "发放本月工资（银行代发）", [
        {"direction": "debit", "account_code": "2211", "account_name": "应付职工薪酬", "amount": monthly_payroll},
        {"direction": "credit", "account_code": "1002", "account_name": "银行存款", "amount": net_payroll},
        {"direction": "credit", "account_code": "222101", "account_name": "应交增值税", "amount": itax},
    ])

    dep = p["monthly_depreciation"]
    add_voucher("transfer", "计提本月固定资产折旧", [
        {"direction": "debit", "account_code": "6602", "account_name": "管理费用", "amount": dep},
        {"direction": "credit", "account_code": "1602", "account_name": "累计折旧", "amount": dep},
    ])

    expense_configs = {
        "6601": {"name": "销售费用", "items": ["市场推广费", "业务招待费", "差旅费", "广告费"],
                 "total": monthly * 0.01, "count": 4},
        "6602": {"name": "管理费用", "items": ["办公用品", "物业费", "水电费", "通讯费", "快递费", "交通费"],
                 "total": monthly * 0.015, "count": 6},
        "6603": {"name": "财务费用", "items": ["银行手续费", "利息支出", "账户管理费"],
                 "total": monthly * 0.005, "count": 3},
    }
    for acct_code, cfg in expense_configs.items():
        per_item = cfg["total"] / cfg["count"] if cfg["count"] > 0 else 0
        for _ in range(cfg["count"]):
            item = random.choice(cfg["items"])
            amt = _amt(per_item, per_item * 0.4, 50)
            add_voucher("payment", f"支付{item}", [
                {"direction": "debit", "account_code": acct_code, "account_name": cfg["name"], "amount": amt},
                {"direction": "credit", "account_code": "1002", "account_name": "银行存款", "amount": amt},
            ])

    actual_output_vat = sum(e["amount"] for v in vouchers for e in v["entries"]
                            if e["account_code"] == "222101" and e["direction"] == "credit")
    actual_input_vat = sum(e["amount"] for v in vouchers for e in v["entries"]
                           if e["account_code"] == "222101" and e["direction"] == "debit")
    net_vat_payable = round(actual_output_vat - actual_input_vat, 2)
    if net_vat_payable > 0:
        add_voucher("transfer", "月末结转未交增值税", [
            {"direction": "debit", "account_code": "222101", "account_name": "应交增值税", "amount": net_vat_payable},
            {"direction": "credit", "account_code": "222102", "account_name": "应交企业所得税（代）", "amount": net_vat_payable},
        ])

    urban = round(net_vat_payable * 0.07, 2)
    edu = round(net_vat_payable * 0.03, 2)
    local_edu = round(net_vat_payable * 0.02, 2)
    stamp = round(monthly_rev_ex_tax * 0.0003, 2)
    surtax_total = round(urban + edu + local_edu + stamp, 2)
    if surtax_total > 0:
        add_voucher("transfer", "计提本月附加税及印花税", [
            {"direction": "debit", "account_code": "6403", "account_name": "税金及附加", "amount": surtax_total},
            {"direction": "credit", "account_code": "222103", "account_name": "应交城市维护建设税", "amount": urban},
            {"direction": "credit", "account_code": "222104", "account_name": "应交教育费附加", "amount": edu},
            {"direction": "credit", "account_code": "222105", "account_name": "应交地方教育附加", "amount": local_edu},
            {"direction": "credit", "account_code": "222106", "account_name": "应交印花税", "amount": stamp},
        ])

    total_revenue = sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6001")
    total_costs = sum(e["amount"] for v in vouchers for e in v["entries"]
                      if e["account_code"] in ("6401", "6601", "6602", "6603", "6403") and e["direction"] == "debit")
    provisional_profit = round(total_revenue - total_costs, 2)
    monthly_income_tax = round(max(0, provisional_profit) * p["income_tax_rate"], 2)
    if monthly_income_tax > 0:
        add_voucher("transfer", "计提本月企业所得税（预缴）", [
            {"direction": "debit", "account_code": "6801", "account_name": "所得税费用", "amount": monthly_income_tax},
            {"direction": "credit", "account_code": "222102", "account_name": "应交企业所得税", "amount": monthly_income_tax},
        ])

    total_expenses = sum(e["amount"] for v in vouchers for e in v["entries"]
                         if e["account_code"] in ("6401", "6403", "6601", "6602", "6603", "6801")
                         and e["direction"] == "debit")
    add_voucher("transfer", "月末结转损益至本年利润", [
        {"direction": "debit", "account_code": "6001", "account_name": "主营业务收入", "amount": total_revenue},
        {"direction": "credit", "account_code": "4103", "account_name": "本年利润", "amount": total_revenue},
        {"direction": "debit", "account_code": "4103", "account_name": "本年利润", "amount": total_expenses},
        {"direction": "credit", "account_code": "6401", "account_name": "主营业务成本", "amount": sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6401" and e["direction"] == "debit")},
        {"direction": "credit", "account_code": "6403", "account_name": "税金及附加", "amount": sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6403" and e["direction"] == "debit")},
        {"direction": "credit", "account_code": "6601", "account_name": "销售费用", "amount": sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6601" and e["direction"] == "debit") or 0},
        {"direction": "credit", "account_code": "6602", "account_name": "管理费用", "amount": sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6602" and e["direction"] == "debit") or 0},
        {"direction": "credit", "account_code": "6603", "account_name": "财务费用", "amount": sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6603" and e["direction"] == "debit") or 0},
        {"direction": "credit", "account_code": "6801", "account_name": "所得税费用", "amount": sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6801" and e["direction"] == "debit") or 0},
    ])

    return vouchers


def build_trial_balance(vouchers: list[dict], p: dict) -> dict:
    turnover: dict[str, dict[str, float]] = {}
    for v in vouchers:
        for e in v["entries"]:
            ac = e["account_code"]
            if ac not in turnover:
                turnover[ac] = {"debit": 0, "credit": 0}
            turnover[ac][e["direction"]] += e["amount"]

    assets = p["total_assets"]
    monthly_rev = p["monthly_revenue"]
    opening_balance = {
        "1001": 50_000, "1002": round(assets * 0.12, 2), "1012": round(assets * 0.02, 2),
        "1122": round(monthly_rev * p["ar_days"] / 30, 2), "1123": round(monthly_rev * 0.08, 2),
        "1221": round(monthly_rev * 0.04, 2),
        "1405": round(monthly_rev * p.get("inventory_days", 60) / 30 * 0.5, 2),
        "1403": round(monthly_rev * 0.05, 2),
        "1601": p["fixed_assets"], "1602": -p["accum_depreciation"],
        "1801": round(assets * 0.04, 2),
        "2001": -round(assets * p.get("current_liability_ratio", 0.7) * 0.2, 2),
        "2202": -round(monthly_rev * p["ap_days"] / 30, 2),
        "2203": -round(monthly_rev * 0.03, 2), "2211": -round(monthly_rev * 0.06, 2),
        "2221": -round(monthly_rev * 0.02, 2), "2241": -round(assets * 0.03, 2),
        "2501": -round(assets * p.get("long_term_debt_ratio", 0.1), 2),
        "4001": -round(assets * 0.40, 2), "4103": -round(p["annual_profit"] * 0.45, 2),
    }

    closing_balance = {}
    for ac, ob in opening_balance.items():
        t = turnover.get(ac, {"debit": 0, "credit": 0})
        closing_balance[ac] = ob + t["debit"] - t["credit"]
    for ac in turnover:
        if ac not in opening_balance:
            t = turnover[ac]
            closing_balance[ac] = t["debit"] - t["credit"]

    return {"period": REPORT_MONTH_LABEL,
            "opening_balance": {k: round(abs(v), 2) for k, v in opening_balance.items()},
            "turnover": {k: {"debit": round(v["debit"], 2), "credit": round(v["credit"], 2)}
                         for k, v in turnover.items()},
            "closing_balance": {k: round(abs(v), 2) for k, v in closing_balance.items()},
            "closing_directions": {k: ("credit" if v < 0 else "debit") for k, v in closing_balance.items()}}


def generate_audit_adjustments(tb: dict, vouchers: list[dict], p: dict) -> dict:
    adj_seq = 0
    def adj_no():
        nonlocal adj_seq; adj_seq += 1
        return f"AJE-{REPORT_YEAR}{REPORT_MONTH:02d}-{adj_seq:02d}"

    adjustments = []
    monthly_rev = p["monthly_revenue"]

    ar_closing = tb["closing_balance"].get("1122", 0)
    long_term_ar = round(ar_closing * 0.15, 2) if ar_closing > 0 else 0
    if long_term_ar > 0:
        adjustments.append({"adj_no": adj_no(), "type": "reclassification",
            "description": "将账龄超过一年的应收账款重分类至长期应收款",
            "entries": [{"direction": "debit", "account_code": "1122", "account_name": "应收账款", "amount": -long_term_ar, "note": "调减"},
                        {"direction": "debit", "account_code": "1221", "account_name": "其他应收款（长期）", "amount": long_term_ar, "note": "重分类调入"}]})

    inv_closing = tb["closing_balance"].get("1405", 0)
    if inv_closing > 10000:
        impairment = round(inv_closing * 0.03, 2)
        adjustments.append({"adj_no": adj_no(), "type": "adjustment",
            "description": "计提存货跌价准备（可变现净值低于账面成本）",
            "entries": [{"direction": "debit", "account_code": "6602", "account_name": "管理费用", "amount": impairment, "note": "计提存货跌价"},
                        {"direction": "credit", "account_code": "1405", "account_name": "库存商品", "amount": -impairment, "note": "冲减库存商品"}]})

    ap_closing = abs(tb["closing_balance"].get("2202", 0))
    if ap_closing > 10000:
        estimate = round(monthly_rev * 0.02, 2)
        adjustments.append({"adj_no": adj_no(), "type": "adjustment",
            "description": "暂估未到票的应付采购款",
            "entries": [{"direction": "debit", "account_code": "1405", "account_name": "库存商品", "amount": estimate, "note": "暂估入库"},
                        {"direction": "credit", "account_code": "2202", "account_name": "应付账款（暂估）", "amount": estimate, "note": "暂估应付"}]})

    adjustments.append({"adj_no": adj_no(), "type": "adjustment",
        "description": "补记截至资产负债表日已发生但未入账的费用",
        "entries": [{"direction": "debit", "account_code": "6602", "account_name": "管理费用", "amount": round(monthly_rev * 0.005, 2), "note": "应计费用"},
                    {"direction": "credit", "account_code": "2241", "account_name": "其他应付款", "amount": round(monthly_rev * 0.005, 2), "note": "预提费用"}]})

    adjustments.append({"adj_no": adj_no(), "type": "adjustment",
        "description": "固定资产折旧测算差异调整（少提折旧补记）",
        "entries": [{"direction": "debit", "account_code": "6602", "account_name": "管理费用", "amount": round(p["monthly_depreciation"] * 0.08, 2), "note": "补提折旧"},
                    {"direction": "credit", "account_code": "1602", "account_name": "累计折旧", "amount": round(p["monthly_depreciation"] * 0.08, 2), "note": "补提折旧"}]})

    return {"audit_period": REPORT_MONTH_LABEL, "adjustments": adjustments,
            "adjustment_count": len(adjustments),
            "audit_conclusion": "经审计调整后，财务报表在所有重大方面公允反映了企业财务状况。"}


def generate_financial_statements(vouchers: list[dict], tb: dict, audit: dict, p: dict) -> dict:
    tr = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6001" and e["direction"] == "credit"), 2)
    tc = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6401" and e["direction"] == "debit"), 2)
    ts = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6403" and e["direction"] == "debit"), 2)
    se = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6601" and e["direction"] == "debit"), 2)
    ae = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6602" and e["direction"] == "debit"), 2)
    fe = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6603" and e["direction"] == "debit"), 2)
    ite = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6801" and e["direction"] == "debit"), 2)
    gp = round(tr - tc, 2)
    op = round(gp - ts - se - ae - fe, 2)
    np = round(op - ite, 2)

    adj_total = sum(sum(e["amount"] for e in adj["entries"]) for adj in audit["adjustments"] if adj["type"] == "adjustment")
    anp = round(np - adj_total, 2)

    income_statement = {"period": REPORT_MONTH_LABEL,
        "items": {"一、营业收入": tr, "减：营业成本": tc, "税金及附加": ts, "销售费用": se, "管理费用": ae,
                  "财务费用": fe, "二、营业利润": op, "减：所得税费用": ite, "三、净利润": np},
        "audit_adjusted": {"审计调整影响": -adj_total, "调整后净利润": anp}}

    closing = tb["closing_balance"]
    ta = round(sum(abs(closing.get(k, 0)) for k in ["1001", "1002", "1012", "1122", "1123", "1221", "1403", "1405", "1601", "1801"]) - abs(closing.get("1602", 0)), 2)
    tl = round(sum(abs(closing.get(k, 0)) for k in ["2001", "2202", "2203", "2211", "2221", "2241", "2501"]), 2)
    te = round(ta - tl, 2)

    balance_sheet = {"period": REPORT_MONTH_LABEL, "total_assets": ta, "total_liabilities": tl, "total_equity": te,
        "items": {"流动资产": round(ta * p["current_asset_ratio"], 2), "非流动资产": round(ta * (1 - p["current_asset_ratio"]), 2),
                  "流动负债": round(tl * p["current_liability_ratio"], 2), "非流动负债": round(tl * (1 - p["current_liability_ratio"]), 2),
                  "所有者权益": te},
        "勾稽验证": {"资产=负债+权益": round(ta - tl - te, 2) == 0, "差额": round(ta - tl - te, 2)}}

    dep_amount = p["monthly_depreciation"]
    ocf = round(np + dep_amount - (closing.get("1122", 0) * 0.08) + (abs(closing.get("2202", 0)) * 0.05), 2)
    icf = round(-p["monthly_depreciation"] * 1.5, 2)
    fcf = round(abs(closing.get("2001", 0)) * 0.02 - abs(closing.get("2501", 0)) * 0.01, 2)

    cash_flow = {"period": REPORT_MONTH_LABEL,
        "items": {"经营活动现金流量净额": ocf, "投资活动现金流量净额": icf, "筹资活动现金流量净额": fcf,
                  "现金及现金等价物净增加额": round(ocf + icf + fcf, 2),
                  "期初现金余额": round(p["total_assets"] * 0.10, 2),
                  "期末现金余额": round(p["total_assets"] * 0.10 + ocf + icf + fcf, 2)}}

    return {"income_statement": income_statement, "balance_sheet": balance_sheet, "cash_flow": cash_flow}


def build_tax_ledger(vouchers: list[dict], p: dict) -> dict:
    ov = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "222101" and e["direction"] == "credit"), 2)
    iv = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "222101" and e["direction"] == "debit"), 2)
    nv = round(ov - iv, 2)
    tr = round(sum(e["amount"] for v in vouchers for e in v["entries"] if e["account_code"] == "6001" and e["direction"] == "credit"), 2)
    total_costs = round(sum(e["amount"] for v in vouchers for e in v["entries"]
                            if e["account_code"] in ("6401", "6601", "6602", "6603", "6403") and e["direction"] == "debit"), 2)
    taxable = round(tr - total_costs, 2)
    itax = round(max(0, taxable) * p["income_tax_rate"], 2)
    urban = round(nv * 0.07, 2)
    edu = round(nv * 0.03, 2)
    local_edu = round(nv * 0.02, 2)
    stamp = round(tr * 0.0003, 2)

    return {"period": REPORT_MONTH_LABEL,
        "vat": {"tax_rate": f"{p['vat_rate']*100:.1f}%", "output_tax": ov, "input_tax": iv,
                "input_tax_deductible": round(iv * 0.95, 2), "net_payable": nv,
                "declared_revenue": tr, "actual_tax_burden": f"{round(nv/tr*100,2)}%" if tr > 0 else "0%"},
        "corporate_income_tax": {"tax_rate": f"{p['income_tax_rate']*100:.1f}%", "taxable_income": taxable,
                                  "tax_payable": itax, "tax_payable_net": itax},
        "surtax": {"urban_construction": urban, "education_surtax": edu,
                    "local_education_surtax": local_edu, "total": round(urban + edu + local_edu, 2)},
        "stamp_duty": {"taxable_amount": tr, "tax_rate": "0.03%", "tax_payable": stamp},
        "total_tax_payable": round(nv + itax + urban + edu + local_edu + stamp, 2)}


def generate_audit_report(et: str, p: dict, fs: dict, audit: dict, tax: dict) -> dict:
    bs = fs["balance_sheet"]; inc = fs["income_statement"]
    return {"report_title": f"{p['name']} 2025年6月财务决算审计报告",
        "report_no": f"安永审字[{REPORT_YEAR}]第{et}{REPORT_MONTH:02d}号",
        "audit_period": REPORT_MONTH_LABEL, "audit_firm": "安永华明会计师事务所（特殊普通合伙）",
        "sections": {"audit_opinion": {"type": "无保留意见",
            "text": f"我们审计了{p['name']}2025年6月的财务报表。我们认为，后附的财务报表在所有重大方面按照企业会计准则的规定编制，公允反映了贵公司2025年6月30日的财务状况以及2025年6月的经营成果和现金流量。"},
            "basis_for_opinion": {"text": "我们按照中国注册会计师审计准则的规定执行了审计工作。我们独立于贵公司，并履行了职业道德方面的其他责任。"},
            "key_audit_matters": [{"matter": "收入确认",
                "description": f"贵公司2025年6月营业收入为{p['monthly_revenue']:,.2f}元。",
                "audit_response": "我们执行了了解和评价内部控制、抽样检查销售合同、实质性分析程序及截止性测试等审计程序。"},
                {"matter": "应收账款减值",
                 "description": f"贵公司应收账款余额约为{p['monthly_revenue']*p['ar_days']/30:,.0f}元。",
                 "audit_response": "我们评估了预期信用损失模型的适当性并执行了独立验证程序。"}],
            "management_responsibility": {"text": "管理层负责按照企业会计准则的规定编制财务报表。"},
            "auditor_responsibility": {"text": "我们的目标是对财务报表整体是否不存在由于舞弊或错误导致的重大错报获取合理保证。"}},
        "financial_highlights": {"total_assets": bs["total_assets"], "total_liabilities": bs["total_liabilities"],
            "total_equity": bs["total_equity"], "asset_liability_ratio": f"{round(bs['total_liabilities']/bs['total_assets']*100,1)}%",
            "monthly_revenue": inc["items"]["一、营业收入"], "monthly_net_profit": inc["items"]["三、净利润"],
            "audit_adjusted_net_profit": inc["audit_adjusted"]["调整后净利润"],
            "tax_burden_summary": tax["vat"]["actual_tax_burden"]},
        "audit_adjustments_summary": [{"no": adj["adj_no"], "type": adj["type"], "desc": adj["description"]} for adj in audit["adjustments"]],
        "report_date": str(date(REPORT_YEAR, 7, 10)), "audit_signature": {"signing_cpa": "王明华", "cert_no": "110000000001"}}


def generate_all_data(et: str) -> dict:
    p = INDUSTRY_PARAMS[et]
    print(f"\n{'='*60}\n  生成 {p['name']} 财务数据\n{'='*60}")
    print("  [1/6] 生成月度会计凭证...")
    vouchers = generate_monthly_vouchers(et, p)
    print(f"        生成了 {len(vouchers)} 张凭证，共 {sum(len(v['entries']) for v in vouchers)} 条分录")
    print("  [2/6] 构建试算平衡表...")
    tb = build_trial_balance(vouchers, p)
    print("  [3/6] 生成审计调整分录...")
    audit = generate_audit_adjustments(tb, vouchers, p)
    print(f"        共 {audit['adjustment_count']} 笔调整/重分类分录")
    print("  [4/6] 生成三张核心财务报表...")
    fs = generate_financial_statements(vouchers, tb, audit, p)
    bs = fs["balance_sheet"]; inc = fs["income_statement"]
    print(f"        净利润: {inc['items']['三、净利润']:,.2f}  总资产: {bs['total_assets']:,.2f}")
    print(f"        勾稽验证: {'通过' if bs['勾稽验证']['资产=负债+权益'] else '失败'}")
    print("  [5/6] 构建税务台账...")
    tax = build_tax_ledger(vouchers, p)
    print(f"        应纳税额合计: {tax['total_tax_payable']:,.2f}")
    print("  [6/6] 编制审计报告...")
    report = generate_audit_report(et, p, fs, audit, tax)
    return {"enterprise_type": et, "enterprise_name": p["name"],
            "monthly_vouchers": vouchers, "trial_balance": tb, "audit_workings": audit,
            "financial_statements": fs, "tax_ledger": tax, "audit_report": report,
            "_summary": {"voucher_count": len(vouchers), "journal_entry_count": sum(len(v["entries"]) for v in vouchers),
                         "total_revenue": inc["items"]["一、营业收入"], "net_profit": inc["items"]["三、净利润"],
                         "total_assets": bs["total_assets"], "total_tax": tax["total_tax_payable"]}}


async def import_to_database(enterprise_types: list[str], force: bool = False):
    from app.database import init_db, AsyncSessionLocal
    from sqlalchemy import select
    from app.models.enterprise import Enterprise
    from app.models.accounting_voucher import AccountingVoucher, JournalEntry, VoucherType, EntryDirection
    from app.models.financial_statement import FinancialStatement, StatementType

    await init_db()
    async with AsyncSessionLocal() as session:
        for et in enterprise_types:
            p = INDUSTRY_PARAMS[et]
            result = await session.execute(select(Enterprise).where(Enterprise.name == p["name"]))
            enterprise = result.scalar_one_or_none()
            if not enterprise:
                print(f"  [SKIP] 企业 '{p['name']}' 不存在于数据库中")
                continue
            if force:
                old_v = await session.execute(select(AccountingVoucher).where(AccountingVoucher.enterprise_id == enterprise.id))
                for v in old_v.scalars(): await session.delete(v)
                old_fs = await session.execute(select(FinancialStatement).where(FinancialStatement.enterprise_id == enterprise.id, FinancialStatement.period == REPORT_MONTH_LABEL))
                for f in old_fs.scalars(): await session.delete(f)
                await session.flush()
                print(f"  [CLEAR] 已清除旧数据")
            data = generate_all_data(et)
            for v_data in data["monthly_vouchers"]:
                voucher = AccountingVoucher(enterprise_id=enterprise.id, voucher_no=v_data["voucher_no"],
                    voucher_date=v_data["voucher_date"], voucher_type=VoucherType(v_data["voucher_type"]),
                    description=v_data["description"], attachment_count=v_data["attachment_count"], is_posted=True, reviewer="系统")
                session.add(voucher); await session.flush()
                for i, e in enumerate(v_data["entries"], 1):
                    entry = JournalEntry(voucher_id=voucher.id, entry_line=i, direction=EntryDirection(e["direction"]),
                        account_code=e["account_code"], account_name=e["account_name"],
                        amount=_d(e["amount"]), description=e.get("note", v_data["description"]), auxiliary=e.get("auxiliary"))
                    session.add(entry)
            print(f"  [OK] 导入 {len(data['monthly_vouchers'])} 张凭证")
            fs = data["financial_statements"]; bs = fs["balance_sheet"]; inc = fs["income_statement"]; cf = fs["cash_flow"]
            tb = data["tax_ledger"]
            for st, fm in [(StatementType.BALANCE_SHEET, {"total_assets": _d(bs["total_assets"]), "total_liabilities": _d(bs["total_liabilities"])}),
                           (StatementType.INCOME_STATEMENT, {"total_revenue": _d(inc["items"]["一、营业收入"]), "total_cost": _d(inc["items"]["减：营业成本"]),
                               "net_profit": _d(inc["items"]["三、净利润"]), "tax_burden_rate": _d(tb["vat"]["net_payable"]/inc["items"]["一、营业收入"]*100) if inc["items"]["一、营业收入"] > 0 else _d(0),
                               "cost_rate": _d(inc["items"]["减：营业成本"]/inc["items"]["一、营业收入"]*100) if inc["items"]["一、营业收入"] > 0 else _d(0)}),
                           (StatementType.CASH_FLOW, {"operating_cash_flow": _d(cf["items"]["经营活动现金流量净额"])})]:
                stmt = FinancialStatement(enterprise_id=enterprise.id, period=REPORT_MONTH_LABEL, statement_type=st,
                    total_assets=fm.get("total_assets", _d(0)), total_liabilities=fm.get("total_liabilities", _d(0)),
                    total_revenue=fm.get("total_revenue", _d(0)), total_cost=fm.get("total_cost", _d(0)),
                    net_profit=fm.get("net_profit", _d(0)), operating_cash_flow=fm.get("operating_cash_flow", _d(0)),
                    tax_burden_rate=fm.get("tax_burden_rate", _d(0)), cost_rate=fm.get("cost_rate", _d(0)))
                session.add(stmt)
            print(f"  [OK] 导入 3 张财务报表")
            await session.commit()
            print(f"  [DONE] {p['name']} 数据导入完成")
    print(f"\n{'='*60}\n  全部数据导入完成\n{'='*60}")


def export_to_json(enterprise_types: list[str], output_dir: str = "generated_financial_data"):
    out_path = Path(output_dir); out_path.mkdir(parents=True, exist_ok=True)
    for et in enterprise_types:
        data = generate_all_data(et); p = INDUSTRY_PARAMS[et]
        fname = out_path / f"{p['name']}_{REPORT_MONTH_LABEL}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        print(f"  [JSON] 已导出到 {fname}")


def main():
    parser = argparse.ArgumentParser(description="财务数据全面生成与导入")
    parser.add_argument("--enterprise", type=str, default="A,B,C,D,E")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--db-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", type=str, default="generated_financial_data")
    args = parser.parse_args()
    enterprise_types = [t.strip() for t in args.enterprise.split(",")]
    valid = set("ABCDE")
    invalid = [t for t in enterprise_types if t not in valid]
    if invalid:
        print(f"无效企业类型: {invalid}, 有效值: A,B,C,D,E"); sys.exit(1)
    print(f"{'='*60}\n  税智·心判 财务数据全面生成\n  报告期间: {REPORT_MONTH_LABEL}  企业数量: {len(enterprise_types)}\n{'='*60}")
    if not args.json_only and not args.db_only:
        export_to_json(enterprise_types, args.output)
        asyncio.run(import_to_database(enterprise_types, args.force))
        print(f"\n完成！JSON 导出至 {args.output}/ ，数据已导入数据库。")
    elif args.db_only:
        asyncio.run(import_to_database(enterprise_types, args.force))
        print("\n完成！数据已导入数据库。")
    else:
        export_to_json(enterprise_types, args.output)
        print(f"\n完成！JSON 已导出至 {args.output}/")


if __name__ == "__main__":
    main()
