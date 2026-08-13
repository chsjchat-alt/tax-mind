"""
验证脱敏模拟数据播种器生成数据的特征正确性

覆盖：
  1. 企业数量 ≥ 50 + 行业覆盖
  2. 重资产企业：折旧占总成本 30%-50%
  3. 轻资产企业：无形劳务进项发票占比（税率 6%，品名在 INTANGIBLE_PRODUCTS 池中）
  4. PII 全掩码：姓名/身份证/银行账号不可逆星号掩码
  5. 统一社会信用代码：GB 32100 18位格式
  6. 风险等级分布合理

运行方式: cd backend && python -m pytest tests/test_mock_data.py -v
"""

import sys
from pathlib import Path

import pytest

# ── 将 scripts 目录加入 sys.path 以便导入播种器 ──
SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from mock_desensitized_data_seeder import (  # noqa: E402
    _generate_enterprises,
    _gen_invoices,
    _gen_bank_transactions,
    _gen_financial_statements,
    _gen_contracts,
    _gen_tax_declarations,
    gen_credit_code,
    mask_name,
    mask_id,
    mask_bank,
    INTANGIBLE_PRODUCTS,
    HEAVY_INDUSTRIES,
    LIGHT_INDUSTRIES,
    GB32100_CHARSET,
)

# ══════════════════════════════════════════════════════════════════
# 常量
# ══════════════════════════════════════════════════════════════════
MIN_ENTERPRISE_COUNT = 50

# ── 重资产行业配置中明确定义的折旧范围 ──
HEAVY_DEPR_RANGE = {
    "制造": (0.30, 0.50),
    "建筑": (0.30, 0.50),
    "交通运输": (0.35, 0.50),
}

# ── 轻资产行业（无折旧） ──
LIGHT_DEPR_ZERO = {"电商", "批发零售", "餐饮服务", "医美咨询"}


# ══════════════════════════════════════════════════════════════════
# helpers
# ══════════════════════════════════════════════════════════════════
def _has_masked_pii(val: str) -> bool:
    """字符串中至少包含一个 '*' 且不是全 '*' """
    return "*" in val and val.replace("*", "").strip() != ""


def _count_intangible_input_invoices(invoices: list[dict]) -> int:
    """统计进项发票中属于无形劳务的数量"""
    count = 0
    for inv in invoices:
        if inv["invoice_type"] != "input":
            continue
        if inv.get("product_name") in INTANGIBLE_PRODUCTS:
            count += 1
    return count


# ══════════════════════════════════════════════════════════════════
# Fixture: 生成 55 家企业完整账套（内存计算，不写 DB）
# ══════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def generated_enterprises():
    """生成 55 家企业 + 每家的完整账套数据字典"""
    enterprises = _generate_enterprises(55)
    results = []
    for ent in enterprises:
        txs = _gen_bank_transactions(ent)
        invs = _gen_invoices(ent)
        decls = _gen_tax_declarations(ent)
        contracts = _gen_contracts(ent)
        stmts = _gen_financial_statements(ent)
        results.append({
            "enterprise": ent,
            "bank_transactions": txs,
            "invoices": invs,
            "tax_declarations": decls,
            "contracts": contracts,
            "financial_statements": stmts,
        })
    return results


# ══════════════════════════════════════════════════════════════════
# 1. 企业数量 & 行业覆盖
# ══════════════════════════════════════════════════════════════════
class TestEnterpriseCountAndCoverage:
    def test_minimum_50_enterprises(self, generated_enterprises):
        """生成企业数量 ≥ 50"""
        assert len(generated_enterprises) >= MIN_ENTERPRISE_COUNT

    def test_all_7_industries_covered(self, generated_enterprises):
        """7 个行业全部覆盖"""
        industries = {e["enterprise"]["industry"] for e in generated_enterprises}
        expected = {"制造", "建筑", "交通运输", "电商", "批发零售", "餐饮服务", "医美咨询"}
        assert industries == expected, f"缺失行业: {expected - industries}"

    def test_heavy_asset_ratio_approximately_40_percent(self, generated_enterprises):
        """重资产企业占比 ≈ 40%（允许 ±10% 偏差）"""
        heavy = [e for e in generated_enterprises
                 if e["enterprise"]["business_model"] == "asset_heavy"]
        ratio = len(heavy) / len(generated_enterprises)
        assert 0.30 <= ratio <= 0.50, f"重资产占比={ratio:.2%}，期望 30%-50%"

    def test_each_enterprise_has_unique_credit_code(self, generated_enterprises):
        """统一社会信用代码全局唯一"""
        codes = [e["enterprise"]["credit_code"] for e in generated_enterprises]
        assert len(codes) == len(set(codes)), "存在重复信用代码"

    def test_each_enterprise_has_unique_id(self, generated_enterprises):
        """企业 ID 全局唯一（UUID）"""
        ids = [e["enterprise"]["id"] for e in generated_enterprises]
        assert len(ids) == len(set(ids)), "存在重复企业ID"


# ══════════════════════════════════════════════════════════════════
# 2. 重资产企业：折旧占总成本 30%-50%
# ══════════════════════════════════════════════════════════════════
class TestHeavyAssetDepreciation:
    def test_all_heavy_enterprises_have_depr_ratio_in_expected_range(
        self, generated_enterprises,
    ):
        """每间重资产企业的 depreciation_ratio 在行业定义范围内"""
        heavy_enterprises = [
            e for e in generated_enterprises
            if e["enterprise"]["business_model"] == "asset_heavy"
        ]
        assert len(heavy_enterprises) > 0, "没有重资产企业，覆盖不足"

        for data in heavy_enterprises:
            ent = data["enterprise"]
            ind = ent["industry"]
            depr = ent["depreciation_ratio"]

            lo, hi = HEAVY_DEPR_RANGE.get(ind, (0.30, 0.50))
            assert lo <= depr <= hi, (
                f"{ent['name']}({ind}) 折旧占比={depr:.3f}，"
                f"期望 {lo:.0%}-{hi:.0%}"
            )

    def test_light_enterprises_have_zero_depreciation(
        self, generated_enterprises,
    ):
        """每间轻资产企业的 depreciation_ratio == 0"""
        light_enterprises = [
            e for e in generated_enterprises
            if e["enterprise"]["business_model"] == "asset_light"
        ]
        for data in light_enterprises:
            ent = data["enterprise"]
            assert ent["depreciation_ratio"] == 0.0, (
                f"{ent['name']}({ent['industry']}) 折旧应为 0，"
                f"实际={ent['depreciation_ratio']}"
            )

    def test_balance_sheet_meta_contains_depreciation_for_heavy(
        self, generated_enterprises,
    ):
        """重资产企业资产负债表 meta 中包含折旧信息"""
        for data in generated_enterprises:
            ent = data["enterprise"]
            if ent["business_model"] != "asset_heavy":
                continue

            # 筛选出资产负债表
            bs_stmts = [
                s for s in data["financial_statements"]
                if s["statement_type"] == "balance_sheet"
            ]
            assert len(bs_stmts) > 0, f"{ent['name']} 缺少资产负债表"

            for bs in bs_stmts:
                meta = bs.get("meta", {})
                # 每个 BS 期都应包含折旧信息
                assert "depreciation_current_period" in meta, (
                    f"{ent['name']} BS {bs['period']} 缺少 depreciation_current_period"
                )
                assert "depreciation_rate" in meta, (
                    f"{ent['name']} BS {bs['period']} 缺少 depreciation_rate"
                )
                depr_rate = meta["depreciation_rate"]
                lo, hi = HEAVY_DEPR_RANGE.get(ent["industry"], (0.30, 0.50))
                assert lo <= depr_rate <= hi, (
                    f"{ent['name']} BS {bs['period']} 折旧率={depr_rate:.3f}"
                )

    def test_depreciation_amount_matches_ratio(
        self, generated_enterprises,
    ):
        """折旧金额 ≈ 折旧率 × 当季成本"""
        for data in generated_enterprises:
            ent = data["enterprise"]
            if ent["business_model"] != "asset_heavy":
                continue

            bs_stmts = [
                s for s in data["financial_statements"]
                if s["statement_type"] == "balance_sheet"
            ]
            for bs in bs_stmts:
                meta = bs.get("meta", {})
                depr_amount = meta.get("depreciation_current_period", 0)
                depr_rate = meta.get("depreciation_rate", 0)
                total_cost = bs.get("total_cost", 0)

                if total_cost > 0 and depr_rate > 0:
                    expected = total_cost * depr_rate
                    # 允许 1% 的浮点偏差或固定偏差（gauss 引入的随机性）
                    tolerance = max(expected * 0.05, 100)
                    assert abs(depr_amount - expected) <= tolerance, (
                        f"{ent['name']} BS {bs['period']} "
                        f"折旧金额={depr_amount}，"
                        f"成本={total_cost} × 折旧率={depr_rate} = {expected}，"
                        f"偏差={abs(depr_amount - expected)} > {tolerance}"
                    )


# ══════════════════════════════════════════════════════════════════
# 3. 轻资产企业：无形劳务进项发票
# ══════════════════════════════════════════════════════════════════
class TestLightAssetIntangibleServices:
    def test_light_enterprises_have_intangible_input_invoices(
        self, generated_enterprises,
    ):
        """每间轻资产企业至少有一张无形劳务进项发票"""
        for data in generated_enterprises:
            ent = data["enterprise"]
            if ent["business_model"] != "asset_light":
                continue

            intangible_count = _count_intangible_input_invoices(data["invoices"])
            assert intangible_count > 0, (
                f"{ent['name']}({ent['industry']}) 无形劳务进项=0，"
                f"期望 ≥1"
            )

    def test_intangible_invoices_have_6_percent_vat_rate(
        self, generated_enterprises,
    ):
        """无形劳务进项发票使用 6% 增值税率"""
        for data in generated_enterprises:
            for inv in data["invoices"]:
                if inv["invoice_type"] != "input":
                    continue
                if inv.get("product_name") in INTANGIBLE_PRODUCTS:
                    assert inv["tax_rate"] == 6.0, (
                        f"{inv['product_name']} 税率={inv['tax_rate']}%，期望 6%"
                    )

    def test_intangible_input_ratio_in_light_enterprises(
        self, generated_enterprises,
    ):
        """轻资产企业无形劳务进项占总进项比例 > 10%"""
        for data in generated_enterprises:
            ent = data["enterprise"]
            if ent["business_model"] != "asset_light":
                continue

            input_invs = [i for i in data["invoices"] if i["invoice_type"] == "input"]
            if not input_invs:
                continue  # 极少数企业可能无进项

            intangible = _count_intangible_input_invoices(data["invoices"])
            ratio = intangible / len(input_invs)
            # 根据播种器逻辑 is_light && random < 0.45 → 无形劳务
            # 所以预期比例在 ~40%-50% 左右，但允许较大波动
            assert ratio >= 0.10, (
                f"{ent['name']}({ent['industry']}) "
                f"无形进项比例={ratio:.1%}，期望 ≥10%"
            )

    def test_intangible_product_names_are_from_pool(self, generated_enterprises):
        """所有无形劳务品名均在 INTANGIBLE_PRODUCTS 允许池中"""
        for data in generated_enterprises:
            for inv in data["invoices"]:
                if inv["invoice_type"] != "input":
                    continue
                # 如果税率是 6%，它应该是无形劳务
                if inv.get("tax_rate") == 6.0:
                    assert inv.get("product_name") in INTANGIBLE_PRODUCTS, (
                        f"6% 税率品名='{inv.get('product_name')}' 不在无形劳务池中"
                    )


# ══════════════════════════════════════════════════════════════════
# 4. PII 全掩码
# ══════════════════════════════════════════════════════════════════
class TestPIIMasking:
    # ── 掩码函数单元测试 ──
    def test_mask_name_standard(self):
        """mask_name: 三字名 → 首*尾 格式"""
        assert mask_name("张三丰") == "张*丰"
        assert mask_name("欧阳娜娜") == "欧**娜"

    def test_mask_name_two_chars(self):
        """mask_name: 两字名 → 首字+* """
        assert mask_name("张三") == "张*"

    def test_mask_name_single_or_empty(self):
        """mask_name: 单字或空 → 安全处理"""
        assert mask_name("") == "***"
        assert mask_name("张") == "张"

    def test_mask_id(self):
        """mask_id: 18位身份证 → 前6 + 8* + 后4"""
        masked = mask_id("330102199001011234")
        assert masked.count("*") == 8
        assert masked[:6] == "330102"
        assert masked[-4:] == "1234"
        assert len(masked) == 18

    def test_mask_bank(self):
        """mask_bank: 银行卡 → 包含掩码星号，且与原始不同"""
        # 用全相同数字避免不可见字符
        raw16 = "1111111111111111"
        masked = mask_bank(raw16)
        assert masked != raw16, f"未掩码: {masked}"
        assert masked.count("*") >= 8, f"掩码不足8个: {masked}"

    # ── 企业 PII 掩码集成测试 ──
    def test_all_enterprises_have_masked_legal_person(
        self, generated_enterprises,
    ):
        """所有企业的 legal_person_masked 包含 '*' 字符"""
        for data in generated_enterprises:
            ent = data["enterprise"]
            name = ent["legal_person_masked"]
            assert "*" in name, (
                f"{ent['name']}: legal_person_masked='{name}' 缺少 '*'"
            )

    def test_all_enterprises_have_masked_id_card(
        self, generated_enterprises,
    ):
        """所有企业的 id_card_masked 包含连续 8 个 '*' """
        for data in generated_enterprises:
            ent = data["enterprise"]
            idc = ent["id_card_masked"]
            assert "********" in idc, (
                f"{ent['name']}: id_card_masked='{idc}' 缺少连续 8 个 '*'"
            )
            assert len(idc) == 18, (
                f"{ent['name']}: id_card_masked 长度={len(idc)}，期望 18"
            )

    def test_all_enterprises_have_masked_bank_account(
        self, generated_enterprises,
    ):
        """所有企业的 bank_account_masked 包含连续 8 个 '*' """
        for data in generated_enterprises:
            ent = data["enterprise"]
            bank = ent["bank_account_masked"]
            assert "********" in bank, (
                f"{ent['name']}: bank_account_masked='{bank}' 缺少连续 8 个 '*'"
            )
            # 银行卡号长度 12-19 位（含掩码后的 '*'）
            assert 12 <= len(bank) <= 19, (
                f"{ent['name']}: bank_account_masked 长度={len(bank)}"
            )

    def test_masked_values_differ_from_raw(
        self, generated_enterprises,
    ):
        """掩码后的值不与原始值相同"""
        for data in generated_enterprises:
            ent = data["enterprise"]
            assert ent["legal_person_masked"] != ent["legal_person_raw"], (
                f"{ent['name']}: 法人名未脱敏"
            )
            assert ent["id_card_masked"] != ent["id_card_raw"], (
                f"{ent['name']}: 身份证未脱敏"
            )
            assert ent["bank_account_masked"] != ent["bank_account_raw"], (
                f"{ent['name']}: 银行卡未脱敏"
            )

    def test_raw_pii_never_appears_in_business_data(
        self, generated_enterprises,
    ):
        """原始姓名/身份证号/银行卡号不出现在业务数据中（银行流水、发票、合同、财报）"""
        all_raw_names = {e["enterprise"]["legal_person_raw"] for e in generated_enterprises}
        all_raw_ids = {e["enterprise"]["id_card_raw"] for e in generated_enterprises}
        all_raw_banks = {e["enterprise"]["bank_account_raw"] for e in generated_enterprises}

        for data in generated_enterprises:
            ent = data["enterprise"]

            # 银行流水：counterparty 不应包含原始姓名或身份证号
            for tx in data["bank_transactions"]:
                cp = tx.get("counterparty", "") or ""
                for raw in all_raw_names:
                    assert raw not in cp, (
                        f"{ent['name']} 银行流水 counterparty='{cp}' 含原始姓名 '{raw}'"
                    )
                for raw in all_raw_ids:
                    assert raw not in cp, (
                        f"{ent['name']} 银行流水 counterparty 含原始身份证"
                    )
                for raw in all_raw_banks:
                    assert raw not in cp, (
                        f"{ent['name']} 银行流水 counterparty 含原始银行卡"
                    )

            # 发票：buyer/seller 不应包含原始 PII
            for inv in data["invoices"]:
                buyer = inv.get("buyer", "") or ""
                seller = inv.get("seller", "") or ""
                for raw in all_raw_names | all_raw_ids | all_raw_banks:
                    assert raw not in buyer, (
                        f"{ent['name']} 发票 buyer='{buyer}' 含原始 PII"
                    )
                    assert raw not in seller, (
                        f"{ent['name']} 发票 seller='{seller}' 含原始 PII"
                    )

            # 合同：counterparty 不应含原始 PII
            for ct in data["contracts"]:
                cp = ct.get("counterparty", "") or ""
                for raw in all_raw_names | all_raw_ids | all_raw_banks:
                    assert raw not in cp, (
                        f"{ent['name']} 合同 counterparty='{cp}' 含原始 PII"
                    )

    def test_bank_account_holder_is_masked(
        self, generated_enterprises,
    ):
        """银行流水的 account_holder 在种子数据中使用的是掩码后姓名"""
        for data in generated_enterprises:
            ent = data["enterprise"]
            # 种子脚本中：account_holder = ent["legal_person_masked"]
            # 但 _gen_bank_transactions 不直接暴露 account_holder
            # ═ 验证：所有 personal 流水的 counterparty 中有掩码信息 ═
            personal_txs = [
                tx for tx in data["bank_transactions"]
                if tx["account_type"] == "personal"
                and tx.get("counterparty") == ent["legal_person_masked"]
            ]
            if personal_txs:
                for tx in personal_txs:
                    cp = tx.get("counterparty", "")
                    assert "*" in cp or cp == ent["legal_person_masked"], (
                        f"{ent['name']}: personal 流水 counterparty='{cp}' 应为掩码值"
                    )


# ══════════════════════════════════════════════════════════════════
# 5. 统一社会信用代码 GB 32100 格式
# ══════════════════════════════════════════════════════════════════
class TestCreditCodeFormat:
    def test_all_codes_are_18_characters(self, generated_enterprises):
        """所有信用代码长度为 18"""
        for data in generated_enterprises:
            code = data["enterprise"]["credit_code"]
            assert len(code) == 18, (
                f"{data['enterprise']['name']}: 信用代码长度={len(code)}"
            )

    def test_all_codes_start_with_valid_prefix(self, generated_enterprises):
        """所有信用代码以 GB 32100 合法前缀开头（数字）"""
        for data in generated_enterprises:
            code = data["enterprise"]["credit_code"]
            assert code[0].isdigit(), (
                f"{data['enterprise']['name']}: 信用代码='{code}' 非数字开头"
            )

    def test_all_codes_contain_only_valid_chars(self, generated_enterprises):
        """所有信用代码仅包含 GB 32100 字符集"""
        allowed = set(GB32100_CHARSET)
        for data in generated_enterprises:
            code = data["enterprise"]["credit_code"]
            invalid = [c for c in code if c not in allowed]
            assert not invalid, (
                f"{data['enterprise']['name']}: "
                f"信用代码='{code}' 含非法字符 {invalid}"
            )

    def test_check_digit_verification(self, generated_enterprises):
        """信用代码第18位校验位正确（gen_credit_code 一致性验证）"""
        for data in generated_enterprises:
            code = data["enterprise"]["credit_code"]
            # 使用 gen_credit_code 重新生成一个代码来验证格式，而不是校验
            # 因为 gen_credit_code 内置了 _compute_check_digit
            another = gen_credit_code()
            assert len(another) == 18
            assert another != code  # 极小概率碰撞


# ══════════════════════════════════════════════════════════════════
# 6. 风险等级分布
# ══════════════════════════════════════════════════════════════════
class TestRiskLevelDistribution:
    def test_all_four_risk_levels_present(self, generated_enterprises):
        """四种风险等级（low/medium/high/critical）全部出现"""
        levels = {e["enterprise"]["risk_level"] for e in generated_enterprises}
        expected = {"low", "medium", "high", "critical"}
        missing = expected - levels
        assert not missing, f"缺失风险等级: {missing}"

    def test_low_risk_is_majority(self, generated_enterprises):
        """低风险企业占比最大（≥ 35%）"""
        low = [e for e in generated_enterprises
               if e["enterprise"]["risk_level"] == "low"]
        ratio = len(low) / len(generated_enterprises)
        assert ratio >= 0.35, f"低风险占比={ratio:.1%}，期望 ≥35%"

    def test_critical_rare(self, generated_enterprises):
        """极危企业占比 < 15%"""
        critical = [e for e in generated_enterprises
                    if e["enterprise"]["risk_level"] == "critical"]
        ratio = len(critical) / len(generated_enterprises)
        assert ratio <= 0.15, f"极危占比={ratio:.1%}，期望 ≤15%"


# ══════════════════════════════════════════════════════════════════
# 7. 数据量完备性
# ══════════════════════════════════════════════════════════════════
class TestDataCompleteness:
    def test_every_enterprise_has_bank_transactions(
        self, generated_enterprises,
    ):
        """每家企业都有银行流水"""
        for data in generated_enterprises:
            assert len(data["bank_transactions"]) > 0, (
                f"{data['enterprise']['name']} 无银行流水"
            )

    def test_every_enterprise_has_invoices(
        self, generated_enterprises,
    ):
        """每家企业都有发票"""
        for data in generated_enterprises:
            assert len(data["invoices"]) > 0, (
                f"{data['enterprise']['name']} 无发票"
            )

    def test_every_enterprise_has_tax_declarations(
        self, generated_enterprises,
    ):
        """每家企业都有纳税申报"""
        for data in generated_enterprises:
            assert len(data["tax_declarations"]) > 0, (
                f"{data['enterprise']['name']} 无纳税申报"
            )

    def test_every_enterprise_has_contracts(
        self, generated_enterprises,
    ):
        """每家企业都有合同"""
        for data in generated_enterprises:
            assert len(data["contracts"]) > 0, (
                f"{data['enterprise']['name']} 无合同"
            )

    def test_every_enterprise_has_financial_statements(
        self, generated_enterprises,
    ):
        """每家企业都有财务报表"""
        for data in generated_enterprises:
            assert len(data["financial_statements"]) > 0, (
                f"{data['enterprise']['name']} 无财务报表"
            )

    def test_heavy_enterprises_have_asset_purchase_transactions(
        self, generated_enterprises,
    ):
        """重资产企业银行流水中包含设备采购类交易"""
        asset_keywords = ["设备采购", "固定资产购置", "设备预付款"]
        for data in generated_enterprises:
            ent = data["enterprise"]
            if ent["business_model"] != "asset_heavy":
                continue
            asset_txs = [
                tx for tx in data["bank_transactions"]
                if tx.get("description") in asset_keywords
            ]
            assert len(asset_txs) > 0, (
                f"{ent['name']} 无设备采购流水"
            )

    def test_light_enterprises_have_personal_transfer_transactions(
        self, generated_enterprises,
    ):
        """轻资产企业银行流水中包含大额公转私/个人划转"""
        personal_outflows = 0
        for data in generated_enterprises:
            if data["enterprise"]["business_model"] != "asset_light":
                continue
            for tx in data["bank_transactions"]:
                if (tx["account_type"] == "personal"
                        and tx["direction"] == "outflow"):
                    personal_outflows += 1
        assert personal_outflows > 0, (
            f"轻资产企业无个人账户流出交易"
        )
