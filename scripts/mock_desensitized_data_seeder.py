"""
行业异质性动态脱敏数据播种器
===============================

根据德勤比赛规则——"禁止使用任何真实企业或个人的保密信息"、
"作品中所有所涉数据须为自行构造的模拟数据，或经脱敏处理至
无法识别特定主体的数据"——

本播种器使用 Python Faker 库动态生成 ≥50 家企业的完整涉税演练账套，
并通过 SQLAlchemy 批量注入 PostgreSQL 数据库。

行业覆盖
--------
  - 重资产 (asset_heavy)：
      制造 / 建筑 / 交通运输
      固定资产折旧占总成本 30%-50%，大额设备采购流水
  - 轻资产 (asset_light)：
      新零售电商 / 批发零售 / 餐饮服务 / 医美咨询
      高频小额无形劳务进项 + 大额个人账户资金划转

安全脱敏红线
------------
  - 统一社会信用代码：GB 32100 虚拟算法生成
  - 法人姓名/身份证/银行账号：不可逆星号掩码（如 "王*明"）
  - 所有数据均为自行构造的模拟数据，不含任何真实保密信息

使用方法
--------
    cd backend
    python ../scripts/mock_desensitized_data_seeder.py
    python ../scripts/mock_desensitized_data_seeder.py --count 10
    python ../scripts/mock_desensitized_data_seeder.py --dry-run
"""

import argparse
import asyncio
import math
import random
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import faker as _fk  # noqa: E402

SEED = 42
random.seed(SEED)
_fk.Faker.seed(SEED)

# ─────────────────────────────────────────────────────────────────
#  GB 32100 虚拟统一社会信用代码生成器
# ─────────────────────────────────────────────────────────────────
REGION_PREFIXES = [
    "91330100", "91440300", "91440100", "91310000",
    "91110100", "91510100", "91320500", "91420100",
    "91370200", "91500100",
]

GB32100_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"

# GB 32100 标准权重（位序1-17），前8位是登记管理机关码，剩余9位是主体标识码
# 但我们对整体使用统一的权重表
_GB_WEIGHTS_FULL = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]


def _compute_check_digit(code_17: str) -> str:
    total = 0
    for i, ch in enumerate(code_17):
        idx = GB32100_CHARSET.index(ch)
        total += _GB_WEIGHTS_FULL[i] * idx
    check = 31 - (total % 31)
    check = 0 if check == 31 else check
    return GB32100_CHARSET[check]


def gen_credit_code(prefix: str | None = None) -> str:
    prefix = prefix or random.choice(REGION_PREFIXES)
    org_code = "".join(random.choices(GB32100_CHARSET, k=9))
    return prefix + org_code + _compute_check_digit(prefix + org_code)


# ─────────────────────────────────────────────────────────────────
#  PII 不可逆星号掩码
# ─────────────────────────────────────────────────────────────────
def mask_name(s: str) -> str:
    if not s or len(s) < 2:
        return s or "***"
    if len(s) == 2:
        return s[0] + "*"
    return s[0] + "*" * (len(s) - 2) + s[-1]


def mask_id(s: str) -> str:
    if not s or len(s) < 10:
        return s or "*" * 18
    return s[:6] + "*" * 8 + s[-4:]


def mask_bank(s: str) -> str:
    if not s or len(s) < 8:
        return s or "*" * 16
    return s[:4] + "*" * (len(s) - 8) + s[-4]


# ─────────────────────────────────────────────────────────────────
#  Faker 实例
# ─────────────────────────────────────────────────────────────────
fake_zh = _fk.Faker("zh_CN")
fake_en = _fk.Faker("en_US")


def fake_person_name() -> str:
    return fake_zh.name()


def fake_id_number() -> str:
    """生成虚拟身份证号（18位，符合校验算法）"""
    area = random.choice(["330102", "440305", "310105", "110108", "510104"])
    dob = fake_en.date_of_birth(minimum_age=35, maximum_age=60).strftime("%Y%m%d")
    seq = f"{random.randint(0, 999):03d}"
    prefix_17 = area + dob + seq
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = "10X98765432"
    total = sum(int(c) * w for c, w in zip(prefix_17, weights))
    check = check_codes[total % 11]
    return prefix_17 + check


def fake_bank_account() -> str:
    """生成虚拟银行卡号（16-19位）"""
    prefixes = ["6222", "6217", "6228", "6230", "6214"]
    return random.choice(prefixes) + "".join(str(random.randint(0, 9)) for _ in range(12))


# ─────────────────────────────────────────────────────────────────
#  行业配置
# ─────────────────────────────────────────────────────────────────
HEAVY_INDUSTRIES = {
    "制造": {
        "model": "asset_heavy",
        "revenue": (15_000_000, 120_000_000),
        "employee": (80, 500),
        "cost_rate": (65.0, 85.0),
        "tax_burden": (2.5, 5.0),
        "depr_ratio": (0.30, 0.50),  # 折旧占总成本 30%-50%
        "private_card": (0.05, 0.20),
        "products": ["电子元器件", "精密模具", "五金配件", "塑胶制品", "钢材",
                     "机械设备", "汽车配件", "化工原料", "纺织面料"],
        "cost_cats": ["原材料采购", "人工费用", "设备折旧", "水电动力",
                      "物流运输", "厂房租金", "设备维护", "检测认证"],
        "capacity": ["产能利用率 82%", "单位能耗 0.45 kWh/件", "设备运转率 91%",
                     "次品率 2.3%", "原料损耗率 1.8%"],
    },
    "建筑": {
        "model": "asset_heavy",
        "revenue": (20_000_000, 150_000_000),
        "employee": (60, 300),
        "cost_rate": (70.0, 95.0),
        "tax_burden": (1.5, 4.0),
        "depr_ratio": (0.30, 0.50),
        "private_card": (0.10, 0.35),
        "products": ["建筑工程", "装修装饰", "市政工程", "土石方工程",
                     "钢结构工程", "幕墙工程", "园林绿化", "机电安装"],
        "cost_cats": ["材料采购", "人工费", "机械租赁", "分包支出",
                      "设备折旧", "项目管理", "安全措施", "招待费用"],
        "capacity": ["施工面积 12万㎡", "完工率 78%", "安全事故率 0.02%",
                     "材料损耗率 3.5%", "机械利用率 85%"],
    },
    "交通运输": {
        "model": "asset_heavy",
        "revenue": (10_000_000, 80_000_000),
        "employee": (50, 300),
        "cost_rate": (60.0, 80.0),
        "tax_burden": (2.0, 4.5),
        "depr_ratio": (0.35, 0.50),
        "private_card": (0.05, 0.15),
        "products": ["公路货运", "城市配送", "冷链运输", "大件运输",
                     "仓储服务", "跨境物流", "多式联运"],
        "cost_cats": ["燃油费", "车辆折旧", "人工费用", "路桥费",
                      "维修保养", "保险费用", "仓储租金", "轮胎耗材"],
        "capacity": ["日均运输里程 380km", "车辆出勤率 92%",
                     "吨公里成本 0.52元", "装卸效率 45件/小时"],
    },
}

LIGHT_INDUSTRIES = {
    "电商": {
        "model": "asset_light",
        "revenue": (5_000_000, 80_000_000),
        "employee": (15, 80),
        "cost_rate": (75.0, 95.0),
        "tax_burden": (1.5, 3.5),
        "private_card": (0.30, 0.60),
        "products": ["服饰鞋包", "美妆护肤", "3C数码", "食品特产",
                     "家居用品", "母婴玩具", "运动户外"],
        "cost_cats": ["商品采购", "平台佣金", "推广费用", "物流配送",
                      "包装耗材", "退换货损耗", "客服外包", "直播推广"],
        "platforms": ["淘宝", "京东", "拼多多", "抖音", "快手", "小红书"],
    },
    "批发零售": {
        "model": "asset_light",
        "revenue": (8_000_000, 60_000_000),
        "employee": (20, 120),
        "cost_rate": (80.0, 95.0),
        "tax_burden": (2.0, 4.0),
        "private_card": (0.20, 0.45),
        "products": ["日用百货", "办公用品", "食品饮料", "家电数码",
                     "建材五金", "服装鞋帽"],
        "cost_cats": ["商品采购", "仓储物流", "人员工资", "店铺租金",
                      "市场推广", "运营管理"],
    },
    "餐饮服务": {
        "model": "asset_light",
        "revenue": (3_000_000, 30_000_000),
        "employee": (15, 80),
        "cost_rate": (85.0, 95.0),
        "tax_burden": (1.0, 3.0),
        "private_card": (0.35, 0.65),
        "products": ["中式正餐", "快餐小吃", "火锅烧烤", "饮品甜品",
                     "外卖配送", "团餐定制"],
        "cost_cats": ["食材采购", "人工费用", "租金水电", "设备维护",
                      "外卖平台佣金", "营销推广", "餐具耗材", "消毒保洁"],
    },
    "医美咨询": {
        "model": "asset_light",
        "revenue": (5_000_000, 50_000_000),
        "employee": (10, 50),
        "cost_rate": (70.0, 90.0),
        "tax_burden": (1.0, 2.5),
        "private_card": (0.50, 0.75),
        "products": ["皮肤管理咨询", "医美营销策划", "品牌代运营",
                     "医生经纪服务", "术前咨询", "术后管理"],
        "cost_cats": ["营销推广", "咨询服务费", "人工费用", "平台佣金",
                      "场地租赁", "设备折旧", "培训费用", "耗材采购"],
        "intangible_services": ["品牌营销策划", "医生IP孵化", "客户管理系统维护",
                                "线上获客方案", "术后回访体系设计",
                                "视觉内容制作", "私域运营方案"],
    },
}

# 轻资产企业无形劳务服务品名池
INTANGIBLE_PRODUCTS = [
    "管理咨询服务", "品牌策划服务", "营销推广服务",
    "信息技术服务", "软件技术服务", "系统运维服务",
    "人力资源服务", "财务咨询服务", "法务咨询服务",
    "设计服务", "广告服务", "会展服务",
    "培训服务", "代理服务", "中介服务",
    "特许权使用费", "版权使用费", "技术服务费",
    "市场调研服务", "客户管理服务",
]

# 企业名称后缀
COMPANY_SUFFIXES = ["有限公司", "股份有限公司", "集团有限公司", "实业有限公司"]


# ─────────────────────────────────────────────────────────────────
#  企业生成
# ─────────────────────────────────────────────────────────────────
def _generate_enterprises(count: int) -> list[dict]:
    """生成指定数量的企业配置"""
    industries = list(HEAVY_INDUSTRIES.items()) + list(LIGHT_INDUSTRIES.items())
    enterprises = []

    # 确保行业覆盖平衡：重资产 40%，轻资产 60%
    heavy_slots = max(1, int(count * 0.4))
    light_slots = count - heavy_slots

    # 分配行业
    heavy_assigned = random.choices(
        list(HEAVY_INDUSTRIES.keys()), k=heavy_slots
    )
    light_assigned = random.choices(
        list(LIGHT_INDUSTRIES.keys()), k=light_slots
    )
    industry_assigned = heavy_assigned + light_assigned
    random.shuffle(industry_assigned)

    for i, ind_name in enumerate(industry_assigned):
        cfg = {**HEAVY_INDUSTRIES.get(ind_name, {}),
               **LIGHT_INDUSTRIES.get(ind_name, {})}
        model = cfg["model"]

        rev_lo, rev_hi = cfg["revenue"]
        revenue = round(random.uniform(rev_lo, rev_hi), 2)
        employees = random.randint(*cfg["employee"])
        cost_rate = round(random.uniform(*cfg["cost_rate"]), 2)
        tax_burden = round(random.uniform(*cfg["tax_burden"]), 2)
        private_ratio = round(random.uniform(*cfg["private_card"]), 2)

        # 风险等级分布 (低:50%, 中:30%, 高:15%, 极危:5%)
        risk_roll = random.random()
        if risk_roll < 0.50:
            risk_level = "low"
            actual_private = round(private_ratio * random.uniform(0.3, 0.6), 2)
            actual_cost_dev = round(random.uniform(1.0, 5.0), 2)
        elif risk_roll < 0.80:
            risk_level = "medium"
            actual_private = round(private_ratio * random.uniform(0.8, 1.2), 2)
            actual_cost_dev = round(random.uniform(8.0, 15.0), 2)
        elif risk_roll < 0.95:
            risk_level = "high"
            actual_private = round(private_ratio * random.uniform(1.2, 1.8), 2)
            actual_cost_dev = round(random.uniform(20.0, 30.0), 2)
        else:
            risk_level = "critical"
            actual_private = round(private_ratio * random.uniform(1.5, 2.2), 2)
            actual_cost_dev = round(random.uniform(30.0, 45.0), 2)

        # PII 生成并脱敏
        raw_name = fake_person_name()
        raw_id = fake_id_number()
        raw_bank = fake_bank_account()

        enterprise = {
            "id": str(uuid.uuid4()),
            "name": _gen_company_name(ind_name),
            "credit_code": gen_credit_code(),
            "industry": ind_name,
            "business_model": model,
            "revenue_annual": Decimal(str(revenue)),
            "employee_count": employees,
            "cost_rate_industry": Decimal(str(cost_rate)),
            "actual_cost_rate": Decimal(str(round(cost_rate + actual_cost_dev, 2))),
            "tax_rate_industry": Decimal(str(tax_burden)),
            "actual_tax_rate": Decimal(str(round(tax_burden * (1 - actual_private * 0.5), 2))),
            "private_card_ratio": Decimal(str(private_ratio)),
            "actual_private_ratio": Decimal(str(round(actual_private, 2))),
            "risk_level": risk_level,
            "is_high_tech": random.random() < 0.08,
            "is_small_micro": revenue < 30_000_000,
            "legal_person_raw": raw_name,
            "legal_person_masked": mask_name(raw_name),
            "id_card_raw": raw_id,
            "id_card_masked": mask_id(raw_id),
            "bank_account_raw": raw_bank,
            "bank_account_masked": mask_bank(raw_bank),
            "depreciation_ratio": round(random.uniform(*cfg.get("depr_ratio", (0.10, 0.20))), 3)
            if model == "asset_heavy" else 0.0,
            "products": list(cfg.get("products", [])),
            "cost_categories": list(cfg.get("cost_cats", [])),
            "capacity_metrics": list(cfg.get("capacity", [])),
            "intangible_services": list(cfg.get("intangible_services", [])),
        }
        enterprises.append(enterprise)

    return enterprises


def _gen_company_name(industry: str) -> str:
    prefix = fake_zh.company_prefix() or fake_zh.city()
    # 使企业名更有行业特征
    industry_keywords = {
        "制造": ["精密制造", "工业科技", "机械", "电子科技", "新材料"],
        "建筑": ["建设工程", "建筑装饰", "市政工程", "土木工程"],
        "交通运输": ["物流", "运输", "供应链管理", "快运"],
        "电商": ["电子商务", "网络科技", "信息科技", "数字科技"],
        "批发零售": ["商贸", "贸易", "供应链", "商业"],
        "餐饮服务": ["餐饮管理", "食品", "饮食文化", "酒店管理"],
        "医美咨询": ["医疗美容", "健康管理", "生物科技", "美学咨询"],
    }
    kw = random.choice(industry_keywords.get(industry, ["科技"]))
    return f"{prefix}{kw}{random.choice(COMPANY_SUFFIXES)}"


# ─────────────────────────────────────────────────────────────────
#  银行流水生成
# ─────────────────────────────────────────────────────────────────
def _gen_bank_transactions(enterprise: dict, months: int = 24) -> list[dict]:
    transactions = []
    annual_rev = float(enterprise["revenue_annual"])
    monthly_rev = annual_rev / 12
    private_ratio = float(enterprise["actual_private_ratio"])
    model = enterprise["business_model"]
    is_light = model == "asset_light"
    depr_ratio = float(enterprise.get("depreciation_ratio", 0))

    # 月交易量
    tx_per_month = random.randint(40, 90)

    for month in range(1, months + 1):
        year = 2024 if month > 12 else 2025
        m = ((month - 1) % 12) + 1

        total = tx_per_month
        personal_count = max(1, int(total * private_ratio))
        corporate_count = total - personal_count

        # ── 公户流水 ──
        for _ in range(corporate_count):
            is_in = random.random() < 0.55
            direction = "inflow" if is_in else "outflow"
            if is_in:
                amt = round(random.gauss(monthly_rev / corporate_count * 1.4,
                                         monthly_rev / corporate_count * 0.5), 2)
                amt = max(100, amt)
                desc = "货款" if random.random() < 0.8 else "预收款"
            else:
                amt = round(random.gauss(monthly_rev * 0.4 / corporate_count,
                                         monthly_rev * 0.1 / corporate_count), 2)
                amt = max(0, amt)
                desc = random.choice(["采购款", "支付货款", "费用报销", "设备款", "租金"])

            d = random.randint(1, 28)
            tx_date = date(year, m, d)
            counterparty = fake_zh.company()

            transactions.append({
                "tx_date": tx_date,
                "amount": amt,
                "direction": direction,
                "account_type": "corporate",
                "counterparty": counterparty,
                "description": desc,
                "is_declared": direction == "outflow" or random.random() < 0.9,
            })

        # ── 个人卡流水 ──
        for _ in range(personal_count):
            is_in = random.random() < (0.85 if is_light else 0.7)
            direction = "inflow" if is_in else "outflow"

            if direction == "outflow":
                # 轻资产企业：大额公转私
                amt = round(random.gauss(80000 if is_light else 30000,
                                         30000 if is_light else 15000), 2)
                amt = max(5000, min(amt, 500000))
                desc = "往来款" if random.random() < 0.5 else "借款"
            else:
                amt = round(random.gauss(monthly_rev * private_ratio / personal_count * 1.5,
                                         monthly_rev * private_ratio / personal_count * 0.3), 2)
                amt = max(500, amt)
                desc = "私卡收款"

            d = random.randint(1, 28)
            tx_date = date(year, m, d)
            counterparty = fake_zh.company()

            transactions.append({
                "tx_date": tx_date,
                "amount": amt,
                "direction": direction,
                "account_type": "personal",
                "counterparty": counterparty,
                "description": desc,
                "is_declared": False,
            })

        # ── 重资产企业：附加设备折旧相关的资产支出流水 ──
        if model == "asset_heavy" and depr_ratio > 0:
            depr_tx_count = max(1, int(corporate_count * depr_ratio * 0.3))
            for _ in range(depr_tx_count):
                amt = round(random.gauss(annual_rev * depr_ratio / 12 / depr_tx_count * 1.5,
                                         annual_rev * depr_ratio / 12 / depr_tx_count * 0.5), 2)
                amt = max(5000, min(amt, 2000000))
                d = random.randint(1, 28)
                transactions.append({
                    "tx_date": date(year, m, d),
                    "amount": amt,
                    "direction": "outflow",
                    "account_type": "corporate",
                    "counterparty": fake_zh.company(),
                    "description": random.choice(["设备采购", "固定资产购置", "设备预付款",
                                                  "维修配件", "检测认证费"]),
                    "is_declared": True,
                })

        # ── 轻资产企业：额外生成大额个人卡划转 ──
        if is_light:
            extra_personal = random.randint(2, 6)
            for _ in range(extra_personal):
                amt = round(random.gauss(120000, 50000), 2)
                amt = max(10000, min(amt, 600000))
                d = random.randint(1, 28)
                transactions.append({
                    "tx_date": date(year, m, d),
                    "amount": amt,
                    "direction": "outflow",
                    "account_type": "personal",
                    "counterparty": enterprise["legal_person_masked"],
                    "description": random.choice(["股东分红", "往来款划转", "个人报销",
                                                  "资金拆借", "利润分配"]),
                    "is_declared": False,
                })

    transactions.sort(key=lambda t: t["tx_date"])
    return transactions


# ─────────────────────────────────────────────────────────────────
#  发票生成
# ─────────────────────────────────────────────────────────────────
def _gen_invoices(enterprise: dict, months: int = 24) -> list[dict]:
    invoices = []
    annual_rev = float(enterprise["revenue_annual"])
    monthly_rev = annual_rev / 12
    model = enterprise["business_model"]
    is_light = model == "asset_light"

    vat_rate = 0.13  # 默认 13%

    for month in range(1, months + 1):
        year = 2024 if month > 12 else 2025
        m = ((month - 1) % 12) + 1

        total = random.randint(15, 45)
        output_count = max(3, int(total * 0.55))
        input_count = total - output_count

        # 销项
        for idx in range(output_count):
            amt = round(random.gauss(monthly_rev / output_count,
                                     monthly_rev * 0.3 / output_count), 2)
            amt = max(100, amt)
            tax = round(amt * vat_rate, 2)
            amount_no_tax = round(amt / (1 + vat_rate), 2)
            product = random.choice(enterprise.get("products", ["商品"]))

            invoices.append({
                "invoice_no": f"FP-{year}-{m:02d}-OS-{idx+1:04d}",
                "invoice_type": "output",
                "invoice_date": date(year, m, random.randint(1, 28)),
                "product_name": product,
                "tax_rate": round(vat_rate * 100, 0),
                "amount": amount_no_tax,
                "tax_amount": tax,
                "total_amount": amt,
                "buyer": fake_zh.company(),
                "seller": enterprise["name"],
                "is_digital": random.random() < 0.6,
            })

        # 进项
        for idx in range(input_count):
            amt = round(random.gauss(monthly_rev * 0.6 / input_count,
                                     monthly_rev * 0.2 / input_count), 2)
            amt = max(100, amt)
            tax = round(amt * vat_rate, 2)
            amount_no_tax = round(amt / (1 + vat_rate), 2)

            # 轻资产企业：大比例无形劳务进项
            if is_light and random.random() < 0.45:
                product = random.choice(INTANGIBLE_PRODUCTS)
                # 无形劳务常为小面额高频
                amt = round(random.gauss(3000, 2000), 2)
                amt = max(500, amt)
                tax = round(amt * 0.06, 2)  # 服务业 6%
                amount_no_tax = round(amt / 1.06, 2)
                tax_rate = 6.0
            else:
                product = random.choice(enterprise.get("products", ["商品"]))
                tax_rate = round(vat_rate * 100, 0)

            invoices.append({
                "invoice_no": f"FP-{year}-{m:02d}-IS-{idx+1:04d}",
                "invoice_type": "input",
                "invoice_date": date(year, m, random.randint(1, 28)),
                "product_name": product,
                "tax_rate": tax_rate,
                "amount": amount_no_tax,
                "tax_amount": tax,
                "total_amount": amt,
                "buyer": enterprise["name"],
                "seller": fake_zh.company(),
                "is_digital": random.random() < 0.6,
            })

    invoices.sort(key=lambda i: i["invoice_date"])
    return invoices


# ─────────────────────────────────────────────────────────────────
#  纳税申报生成
# ─────────────────────────────────────────────────────────────────
def _gen_tax_declarations(enterprise: dict, quarters: int = 8) -> list[dict]:
    declarations = []
    annual_rev = float(enterprise["revenue_annual"])
    actual_tax_rate = float(enterprise["actual_tax_rate"])
    private_ratio = float(enterprise["actual_private_ratio"])

    target_annual_tax = annual_rev * actual_tax_rate / 100.0
    seasonal = [0.22, 0.25, 0.23, 0.30]

    for q in range(1, quarters + 1):
        y = 2024 if q > 4 else 2025
        qi = ((q - 1) % 4)
        sf = seasonal[qi]
        q_revenue = annual_rev * sf
        hide_ratio = private_ratio * random.uniform(0.8, 1.2)
        declared_rev = q_revenue * (1 - hide_ratio)
        q_tax_target = target_annual_tax * sf

        period = f"{y}-Q{qi+1}"

        # 增值税 55%
        vat = round(q_tax_target * 0.55 * random.uniform(0.92, 1.08), 2)
        declarations.append({
            "tax_type": "vat",
            "period": f"{period}-VAT",
            "declared_revenue": round(declared_rev, 2),
            "declared_tax": vat,
            "actual_paid": round(vat * random.uniform(0.95, 1.0), 2),
            "declaration_date": date(y, qi * 3 + 3, random.randint(10, 15)),
        })

        # 企业所得税 35%
        itax = round(q_tax_target * 0.35 * random.uniform(0.92, 1.08), 2)
        declarations.append({
            "tax_type": "income_tax",
            "period": f"{period}-IT",
            "declared_revenue": round(declared_rev, 2),
            "declared_tax": itax,
            "actual_paid": round(itax * random.uniform(0.95, 1.0), 2),
            "declaration_date": date(y, qi * 3 + 3, random.randint(10, 15)),
        })

        # 个人所得税 10%
        pit = round(q_tax_target * 0.10 * random.uniform(0.92, 1.08), 2)
        declarations.append({
            "tax_type": "personal_income_tax",
            "period": f"{period}-PAX",
            "declared_revenue": 0.0,
            "declared_tax": pit,
            "actual_paid": round(pit * random.uniform(0.95, 1.0), 2),
            "declaration_date": date(y, qi * 3 + 3, random.randint(10, 15)),
        })

    return declarations


# ─────────────────────────────────────────────────────────────────
#  合同 & 财务报表
# ─────────────────────────────────────────────────────────────────
def _gen_contracts(enterprise: dict) -> list[dict]:
    contracts = []
    total = random.randint(15, 35)
    annual_rev = float(enterprise["revenue_annual"])
    avg_contract = annual_rev / (total * 0.55)

    for idx in range(1, total + 1):
        is_sales = idx <= int(total * 0.55)
        c_type = "sales" if is_sales else "purchase"
        amt = round(random.gauss(avg_contract, avg_contract * 0.4), 2)
        amt = max(5000, amt)
        m = random.randint(1, 12)
        status_w = [0.6, 0.25, 0.15]
        if enterprise["risk_level"] in ("high", "critical"):
            status_w = [0.35, 0.25, 0.40]
        status = random.choices(["履约完成", "履行中", "终止/争议"], weights=status_w, k=1)[0]

        contracts.append({
            "contract_no": f"{'XS' if is_sales else 'CG'}-2025-{idx:04d}",
            "contract_type": c_type,
            "counterparty": fake_zh.company(),
            "contract_amount": amt,
            "signing_date": date(2025, m, random.randint(1, 28)),
            "execution_status": status,
        })

    contracts.sort(key=lambda c: c["signing_date"])
    return contracts


def _gen_financial_statements(enterprise: dict, quarters: int = 8) -> list[dict]:
    statements = []
    annual_rev = float(enterprise["revenue_annual"])
    cost_rate = float(enterprise["actual_cost_rate"])
    tax_burden = float(enterprise["actual_tax_rate"])
    model = enterprise["business_model"]
    depr_ratio = float(enterprise.get("depreciation_ratio", 0))

    risk_liab_map = {"low": 0.45, "medium": 0.62, "high": 0.78, "critical": 0.88}
    liab_ratio = risk_liab_map.get(enterprise["risk_level"], 0.50)

    seasonal = [0.22, 0.25, 0.23, 0.30]

    for q in range(1, quarters + 1):
        y = 2024 if q > 4 else 2025
        qi = ((q - 1) % 4)
        sf = seasonal[qi] + random.uniform(-0.03, 0.03)
        q_revenue = round(annual_rev * sf, 2)
        q_cost = round(q_revenue * cost_rate / 100.0, 2)
        q_profit = round(q_revenue - q_cost, 2)
        total_assets = round(annual_rev * 0.9 * sf * 4, 2)
        total_liab = round(total_assets * liab_ratio, 2)

        period = f"{y}-Q{qi+1}"

        # 资产负债表（含折旧信息）
        depr_amount = round(q_cost * depr_ratio, 2) if depr_ratio > 0 else 0
        meta = {}
        if model == "asset_heavy":
            meta = {
                "fixed_assets_net": round(total_assets * 0.55, 2),
                "depreciation_current_period": depr_amount,
                "depreciation_rate": depr_ratio,
                "capacity_utilization": random.choice(enterprise.get("capacity_metrics", ["N/A"])),
            }

        statements.append({
            "period": f"{period}-BS",
            "statement_type": "balance_sheet",
            "total_assets": total_assets,
            "total_liabilities": total_liab,
            "total_revenue": q_revenue,
            "total_cost": q_cost,
            "net_profit": q_profit,
            "operating_cash_flow": round(q_revenue * 0.75, 2),
            "tax_burden_rate": tax_burden,
            "cost_rate": cost_rate,
            "meta": meta,
        })

        statements.append({
            "period": f"{period}-PL",
            "statement_type": "income_statement",
            "total_assets": 0.0,
            "total_liabilities": 0.0,
            "total_revenue": q_revenue,
            "total_cost": q_cost,
            "net_profit": q_profit,
            "operating_cash_flow": 0.0,
            "tax_burden_rate": tax_burden,
            "cost_rate": cost_rate,
            "meta": {},
        })

        statements.append({
            "period": f"{period}-CF",
            "statement_type": "cash_flow",
            "total_assets": 0.0,
            "total_liabilities": 0.0,
            "total_revenue": q_revenue,
            "total_cost": q_cost,
            "net_profit": 0.0,
            "operating_cash_flow": round(q_revenue * 0.72, 2),
            "tax_burden_rate": tax_burden,
            "cost_rate": cost_rate,
            "meta": {},
        })

    return statements


# ─────────────────────────────────────────────────────────────────
#  PostgreSQL 批量注入
# ─────────────────────────────────────────────────────────────────
async def _seed_to_db(enterprises: list[dict], dry_run: bool = False):
    from sqlalchemy import select
    from app.database import engine, AsyncSessionLocal, Base
    from app.models.enterprise import Enterprise, IndustryType, RiskLevelEnhanced
    from app.models.bank_transaction import BankTransaction, DirectionType, AccountType
    from app.models.invoice import Invoice, InvoiceType
    from app.models.tax_declaration import TaxDeclaration, TaxType
    from app.models.contract import Contract, ContractType
    from app.models.financial_statement import FinancialStatement, StatementType

    # 确保表存在
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    industry_map = {
        "制造": IndustryType.MANUFACTURING,
        "建筑": IndustryType.CONSTRUCTION,
        "交通运输": IndustryType.MANUFACTURING,  # 暂归入制造
        "电商": IndustryType.E_COMMERCE,
        "批发零售": IndustryType.WHOLESALE_RETAIL,
        "餐饮服务": IndustryType.CATERING,
        "医美咨询": IndustryType.E_COMMERCE,  # 暂归入电商
    }
    risk_map = {
        "low": RiskLevelEnhanced.LOW,
        "medium": RiskLevelEnhanced.MEDIUM,
        "high": RiskLevelEnhanced.HIGH,
        "critical": RiskLevelEnhanced.CRITICAL,
    }

    if dry_run:
        print("\n[DRY RUN] 跳过数据库写入")
        _print_summary(enterprises)
        return

    print("\n开始批量写入数据库...")
    total_enterprises = len(enterprises)
    total_tx = 0
    total_inv = 0
    total_decl = 0
    total_contracts = 0
    total_fs = 0

    async with AsyncSessionLocal() as session:
        for i, ent in enumerate(enterprises):
            print(f"  [{i+1}/{total_enterprises}] {ent['name']} ({ent['industry']})")

            # 企业
            e = Enterprise(
                id=ent["id"],
                name=ent["name"],
                credit_code=ent["credit_code"],
                industry=industry_map.get(ent["industry"], IndustryType.WHOLESALE_RETAIL),
                revenue_annual=ent["revenue_annual"],
                employee_count=ent["employee_count"],
                tax_rate_claimed=ent["actual_tax_rate"],
                cost_rate_claimed=ent["actual_cost_rate"],
                is_high_tech=ent["is_high_tech"],
                is_small_micro=ent["is_small_micro"],
                risk_level=risk_map.get(ent["risk_level"], RiskLevelEnhanced.LOW),
            )
            session.add(e)

            # 银行流水
            txs = _gen_bank_transactions(ent)
            for tx in txs:
                bt = BankTransaction(
                    id=str(uuid.uuid4()),
                    enterprise_id=ent["id"],
                    transaction_date=tx["tx_date"],
                    amount=Decimal(str(tx["amount"])),
                    direction=DirectionType.INFLOW if tx["direction"] == "inflow" else DirectionType.OUTFLOW,
                    account_type=AccountType.CORPORATE if tx["account_type"] == "corporate" else AccountType.PERSONAL,
                    account_holder=ent["legal_person_masked"],
                    counterparty=tx.get("counterparty"),
                    description=tx.get("description"),
                    is_declared=tx.get("is_declared", True),
                )
                session.add(bt)
                total_tx += 1

            # 发票
            invs = _gen_invoices(ent)
            for inv in invs:
                invoice = Invoice(
                    id=str(uuid.uuid4()),
                    enterprise_id=ent["id"],
                    invoice_no=inv["invoice_no"],
                    invoice_type=InvoiceType.OUTPUT if inv["invoice_type"] == "output" else InvoiceType.INPUT,
                    invoice_date=inv["invoice_date"],
                    amount=Decimal(str(inv["amount"])),
                    tax_amount=Decimal(str(inv["tax_amount"])),
                    total_amount=Decimal(str(inv["total_amount"])),
                    product_name=inv.get("product_name"),
                    buyer_name=inv.get("buyer"),
                    seller_name=inv.get("seller"),
                    is_digital=inv.get("is_digital", False),
                )
                session.add(invoice)
                total_inv += 1

            # 纳税申报
            decls = _gen_tax_declarations(ent)
            tax_type_map = {"vat": TaxType.VAT, "income_tax": TaxType.INCOME_TAX, "personal_income_tax": TaxType.PERSONAL_INCOME_TAX}
            for decl in decls:
                td = TaxDeclaration(
                    id=str(uuid.uuid4()),
                    enterprise_id=ent["id"],
                    tax_type=tax_type_map[decl["tax_type"]],
                    period=decl["period"],
                    declared_revenue=Decimal(str(decl["declared_revenue"])),
                    declared_tax=Decimal(str(decl["declared_tax"])),
                    actual_paid=Decimal(str(decl["actual_paid"])),
                    declaration_date=decl["declaration_date"],
                )
                session.add(td)
                total_decl += 1

            # 合同
            cts = _gen_contracts(ent)
            for ct in cts:
                contract = Contract(
                    id=str(uuid.uuid4()),
                    enterprise_id=ent["id"],
                    contract_no=ct["contract_no"],
                    contract_type=ContractType.SALES if ct["contract_type"] == "sales" else ContractType.PURCHASE,
                    counterparty=ct["counterparty"],
                    contract_amount=Decimal(str(ct["contract_amount"])),
                    signing_date=ct["signing_date"],
                    execution_status=ct["execution_status"],
                )
                session.add(contract)
                total_contracts += 1

            # 财务报表
            stmts = _gen_financial_statements(ent)
            stmt_type_map = {"balance_sheet": StatementType.BALANCE_SHEET, "income_statement": StatementType.INCOME_STATEMENT, "cash_flow": StatementType.CASH_FLOW}
            for stmt in stmts:
                fs = FinancialStatement(
                    id=str(uuid.uuid4()),
                    enterprise_id=ent["id"],
                    period=stmt["period"],
                    statement_type=stmt_type_map[stmt["statement_type"]],
                    total_assets=Decimal(str(stmt["total_assets"])),
                    total_liabilities=Decimal(str(stmt["total_liabilities"])),
                    total_revenue=Decimal(str(stmt["total_revenue"])),
                    total_cost=Decimal(str(stmt["total_cost"])),
                    net_profit=Decimal(str(stmt["net_profit"])),
                    operating_cash_flow=Decimal(str(stmt["operating_cash_flow"])),
                    tax_burden_rate=Decimal(str(stmt["tax_burden_rate"])),
                    cost_rate=Decimal(str(stmt["cost_rate"])),
                )
                session.add(fs)
                total_fs += 1

            # 批量刷新（每5家企业提交一次，避免内存爆炸）
            if (i + 1) % 5 == 0:
                await session.flush()
                print(f"    已刷新 {i+1}/{total_enterprises} 家企业")

        await session.flush()
        await session.commit()

    print(f"\n数据库写入完成:")
    print(f"  企业: {total_enterprises}")
    print(f"  银行流水: {total_tx} 条")
    print(f"  发票: {total_inv} 张")
    print(f"  纳税申报: {total_decl} 条")
    print(f"  合同: {total_contracts} 份")
    print(f"  财务报表: {total_fs} 份")


def _print_summary(enterprises: list[dict]):
    """打印生成摘要（dry-run 模式）"""
    total_tx = 0
    total_inv = 0
    total_decl = 0

    heavy_count = sum(1 for e in enterprises if e["business_model"] == "asset_heavy")
    light_count = sum(1 for e in enterprises if e["business_model"] == "asset_light")

    for ent in enterprises:
        risk = ent["risk_level"]
        model = "重资产" if ent["business_model"] == "asset_heavy" else "轻资产"
        depr = f" 折旧{ent['depreciation_ratio']*100:.0f}%" if ent["depreciation_ratio"] > 0 else ""

        print(f"  [{model}] {ent['name'][:25]:25s} | {ent['industry']:6s} | "
              f"营收{float(ent['revenue_annual'])/10000:.0f}万 | {risk:8s}{depr}")
        print(f"    法人: {ent['legal_person_masked']}  "
              f"身份证: {ent['id_card_masked']}  "
              f"银行卡: {ent['bank_account_masked']}")

        txs = _gen_bank_transactions(ent)
        invs = _gen_invoices(ent)
        decls = _gen_tax_declarations(ent)
        total_tx += len(txs)
        total_inv += len(invs)
        total_decl += len(decls)

    print(f"\n{'─'*60}")
    print(f"  模拟数据生成摘要")
    print(f"{'─'*60}")
    print(f"  企业总数:     {len(enterprises)}")
    print(f"    重资产:     {heavy_count} 家 (制造/建筑/交通运输)")
    print(f"    轻资产:     {light_count} 家 (电商/批发零售/餐饮/医美)")
    print(f"  银行流水:     ~{total_tx} 条 (24个月)")
    print(f"  发票:         ~{total_inv} 张 (24个月)")
    print(f"  纳税申报:     ~{total_decl} 条 (8个季度)")
    print(f"  合同:         ~{light_count * 25} 份")
    print(f"  财务报表:     ~{len(enterprises) * 24} 份")

    # 脱敏验证
    print(f"\n{'─'*60}")
    print(f"  脱敏验证（抽样）")
    print(f"{'─'*60}")
    sample = enterprises[0]
    print(f"  姓名:  {sample['legal_person_raw']} → {sample['legal_person_masked']}")
    print(f"  身份证: {sample['id_card_raw']} → {sample['id_card_masked']}")
    print(f"  银行卡: {sample['bank_account_raw']} → {sample['bank_account_masked']}")
    print(f"  信用代码: {sample['credit_code']}")
    print()
    print("  [确认] 以上所有数据均为自行构造的模拟数据，不包含任何真实企业或个人保密信息。")


# ─────────────────────────────────────────────────────────────────
#  CLI 入口
# ─────────────────────────────────────────────────────────────────
async def main(count: int, dry_run: bool = False):
    print("=" * 60)
    print("  税智·心判 — 行业异质性动态脱敏数据播种器")
    print("=" * 60)
    print()
    print("【重要安全声明】")
    print("根据德勤比赛规则：")
    print("  - 禁止使用任何真实企业或个人的保密信息")
    print("  - 所有涉税数据须为自行构造的模拟数据")
    print("  - 或经脱敏处理至无法识别特定主体的数据")
    print()
    print("本播种器使用 Python Faker 动态生成：")
    print("  - GB 32100 虚拟统一社会信用代码")
    print("  - 不可逆星号掩码的法人姓名/身份证/银行账号")
    print("  - 正向分布重资产企业（折旧 30%-50% 总成本）")
    print("  - 轻资产企业高频无形劳务进项 + 大额公转私流水")
    print()

    # 生成企业
    print(f"正在生成 {count} 家企业数据...")
    enterprises = _generate_enterprises(count)

    if dry_run:
        _print_summary(enterprises)
        return

    await _seed_to_db(enterprises, dry_run=False)

    print(f"\n{'=' * 60}")
    print(f"  数据播种完成！共生成 {count} 家企业的涉税演练账套")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="税智·心判 行业异质性动态脱敏数据播种器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--count", type=int, default=50, help="企业数量 (默认: 50)")
    parser.add_argument("--dry-run", action="store_true", help="仅预览数据不入库")
    args = parser.parse_args()

    asyncio.run(main(args.count, args.dry_run))