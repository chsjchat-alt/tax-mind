"""
乳业农产品核定扣除引擎测试（对应 V4 §4.2 + §九验收指标）

覆盖：
  - 抵扣路径判定（试点身份优先；非试点三情形 + 合作社；未知凭证转人工）
  - 产品『鲜奶』范围判定（巴氏/灭菌 ∈；酸奶/调制乳 ∉；未知转人工）
  - 单耗标准库（38号文附件2 六系数 + 羊乳）
  - Decimal 金额计算（投入产出法/成本法/普通路径）与重算一致率 100%
"""
from datetime import date
from decimal import Decimal

import pytest

from app.core.deemed_deduction import (
    DeemedCalcRequest,
    RuleExecutor,
    calc_cost_method,
    calc_input_output_method,
    calc_invoice_path_amount,
    classify_product_scope,
    identify_purchase_path,
    pick_coefficient,
    run_deemed_calculation,
)

ON_DATE = date(2026, 9, 12)


# ── 抵扣路径（V3.1 采纳 E2-C：试点范围内不得自由二选一） ──
class TestPathIdentification:
    def test_pilot_entity_goes_deemed(self) -> None:
        path = identify_purchase_path(True, "sales_or_purchase_invoice")
        assert path.path_code == "deemed" and path.rule_id == "AGRI-DEEM-001"

    def test_non_pilot_sales_invoice_9pct(self) -> None:
        path = identify_purchase_path(False, "sales_or_purchase_invoice")
        assert path.path_code == "sales_or_purchase_invoice"
        assert path.rate == Decimal("0.09")
        assert "买价" in path.basis

    def test_non_pilot_small_scale_3pct_9pct(self) -> None:
        path = identify_purchase_path(False, "small_scale_3pct_special_invoice")
        assert path.rate == Decimal("0.09")

    def test_non_pilot_general_invoice_no_rate(self) -> None:
        """①情形：凭注明税额，引擎不代算"""
        path = identify_purchase_path(False, "general_vat_invoice_or_customs")
        assert path.rate is None and "注明" in path.basis

    def test_coop_exempt_9pct(self) -> None:
        assert identify_purchase_path(False, "coop_exempt_product").rate == Decimal("0.09")

    def test_unknown_voucher_manual(self) -> None:
        assert identify_purchase_path(False, "mystery").path_code == "manual"


# ── 产品『鲜奶』范围（2026年第9号公告附件1；四个演示用例） ──
class TestProductScope:
    @pytest.mark.parametrize("name", ["巴氏杀菌乳", "巴氏鲜奶(250ml)", "灭菌乳", "UHT乳"])
    def test_in_scope(self, name: str) -> None:
        assert classify_product_scope(name).in_scope is True

    @pytest.mark.parametrize("name", ["酸奶", "风味发酵乳", "调制乳", "奶酪", "稀奶油"])
    def test_out_scope(self, name: str) -> None:
        """G2 采纳：加工奶制品/调制乳不得直接套用『鲜奶』9%"""
        assert classify_product_scope(name).in_scope is False

    def test_unknown_routes_manual(self) -> None:
        assert classify_product_scope("乳铁蛋白口服液").in_scope is None


# ── 单耗标准库（38号文附件2 六项全国统一标准） ──
class TestCoefficients:
    @pytest.mark.parametrize(
        ("kind", "animal", "hp", "expected", "rule_id"),
        [
            ("uht", "cow", False, "1.068", "AGRI-DEEM-COF-001"),
            ("uht", "cow", True, "1.124", "AGRI-DEEM-COF-002"),
            ("pasteurized", "cow", False, "1.055", "AGRI-DEEM-COF-003"),
            ("pasteurized", "cow", True, "1.196", "AGRI-DEEM-COF-004"),
            ("uht", "goat", False, "1.023", "AGRI-DEEM-COF-005"),
            ("pasteurized", "goat", False, "1.062", "AGRI-DEEM-COF-006"),
        ],
    )
    def test_national_coefficients(
        self, kind: str, animal: str, hp: bool, expected: str, rule_id: str
    ) -> None:
        coef, rid = pick_coefficient(kind, animal, hp)
        assert coef == Decimal(expected) and rid == rule_id

    def test_goat_high_protein_no_standard(self) -> None:
        """羊乳高蛋白无全国统一标准 → (None) 由省级/个案核定场景接手"""
        coef, rid = pick_coefficient("uht", "goat", True)
        assert coef is None and rid == ""


# ── Decimal 金额计算（法定公式） ──
class TestAmountCalculation:
    def test_input_output_method(self) -> None:
        """1000吨 × 1.068 × 3.5万/吨 × 9% / 1.09 = 308.64（Decimal 精确）"""
        vat, formula = calc_input_output_method(
            Decimal("1000"), Decimal("1.068"), Decimal("3.5"), Decimal("0.09")
        )
        assert vat == Decimal("308.64")
        assert "投入产出法" in formula and "38号附件1" in formula

    def test_cost_method(self) -> None:
        """500000 × 0.62 × 9% / 1.09 = 25596.33"""
        vat, formula = calc_cost_method(
            Decimal("500000"), Decimal("0.62"), Decimal("0.09")
        )
        assert vat == Decimal("25596.33")
        assert "成本法" in formula

    def test_invoice_path_amount(self) -> None:
        """③买价 10000 × 9% = 900.00"""
        vat, formula = calc_invoice_path_amount(Decimal("10000"), Decimal("0.09"))
        assert vat == Decimal("900.00") and "VAT-INPUT-STD-001" in formula


# ── 端到端：run_deemed_calculation ──
class TestEndToEnd:
    @pytest.fixture()
    def executor(self) -> RuleExecutor:
        return RuleExecutor()

    def _pilot_request(self, product_name: str = "巴氏杀菌乳") -> DeemedCalcRequest:
        return DeemedCalcRequest(
            entity_is_pilot=True,
            product_kind="pasteurized",
            animal="cow",
            high_protein=False,
            sales_quantity=Decimal("1000"),
            avg_purchase_price=Decimal("3.5"),
            product_name=product_name,
        )

    def test_pilot_auto_full_chain(self, executor: RuleExecutor) -> None:
        """试点 + 巴氏杀菌乳 → 全链自动：单耗1.055、扣除率9%、进项税额 305.34"""
        result = run_deemed_calculation(self._pilot_request(), executor, ON_DATE)
        assert result.route == "auto"
        assert result.coefficient == Decimal("1.055")
        assert result.rate == Decimal("0.09")
        # 1000 × 1.055 × 3.5 = 3692.5（买价）；× 0.09/1.09 = 304.8853... → 304.89
        assert result.input_vat == Decimal("304.89")
        assert result.calc_id
        assert "AGRI-DEEM-RATE-001" in result.rule_ids
        assert any("不得改按普通凭票路径" in n for n in result.notes)

    def test_yogurt_routes_manual(self, executor: RuleExecutor) -> None:
        """酸奶：范围外 → 转人工，禁止默认套用 9%"""
        req = self._pilot_request(product_name="风味发酵乳")
        result = run_deemed_calculation(req, executor, ON_DATE)
        assert result.route == "manual" and "不属于" in result.reason

    def test_unknown_product_manual(self, executor: RuleExecutor) -> None:
        result = run_deemed_calculation(
            self._pilot_request(product_name="燕麦奶"), executor, ON_DATE
        )
        assert result.route == "manual"

    def test_non_pilot_invoice_path(self, executor: RuleExecutor) -> None:
        """非试点 + 收购发票：买价口径 10000×9%=900（演示：avg_purchase_price 传计税基础）"""
        req = DeemedCalcRequest(
            entity_is_pilot=False,
            product_kind="pasteurized", animal="cow", high_protein=False,
            sales_quantity=Decimal("0"),
            avg_purchase_price=Decimal("10000"),
            voucher_type="sales_or_purchase_invoice",
        )
        result = run_deemed_calculation(req, executor, ON_DATE)
        assert result.route == "auto"
        assert result.input_vat == Decimal("900.00")
        assert result.rule_ids == ("VAT-INPUT-STD-001",)

    def test_reproducibility_100pct(self, executor: RuleExecutor) -> None:
        """验收指标：同源输入重算一致率 100%"""
        r1 = run_deemed_calculation(self._pilot_request(), executor, ON_DATE)
        r2 = run_deemed_calculation(self._pilot_request(), executor, ON_DATE)
        assert r1.calc_id == r2.calc_id and r1.input_vat == r2.input_vat
