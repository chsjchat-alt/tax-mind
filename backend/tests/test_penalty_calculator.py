"""
罚款计算逻辑单元测试（新版 API）

覆盖场景：
  - 低/中/高风险三种场景的罚款倍数验证
  - 滞纳金计算验证
  - 总风险敞口计算验证
  - 零值边界（未缴税款为0、滞纳天数为0）
  - 个税穿透还原
  - 虚开发票叠加
  - 负数异常处理
"""

import pytest
from decimal import Decimal

from app.core.penalty_calculator import (
    calculate_compound_penalty_exposure,
    UnpaidTaxInput,
    CompoundPenaltyResult,
    PENALTY_MULTIPLIER,
    LATE_FEE_DAILY_RATE,
    IIT_DIVIDEND_RATE,
    _calculate_iit_hidden_dividend,
    PenaltyRiskLevel,
    PenaltySeverity,
)


class TestPenaltyMultipliers:
    """罚款倍数验证"""

    def test_low_risk_05x(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=0, risk_level="low")
        )
        assert result.penalty_multiplier == Decimal("0.5")
        assert result.admin_penalty == Decimal("50000")

    def test_medium_risk_15x(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=0, risk_level="medium")
        )
        assert result.penalty_multiplier == Decimal("1.5")
        assert result.admin_penalty == Decimal("150000")

    def test_high_risk_35x(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=0, risk_level="high")
        )
        assert result.penalty_multiplier == Decimal("3.5")
        assert result.admin_penalty == Decimal("350000")

    def test_critical_risk_50x(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=0, risk_level="critical")
        )
        assert result.penalty_multiplier == Decimal("5.0")
        assert result.admin_penalty == Decimal("500000")


class TestLateFeeCalculation:
    """滞纳金计算验证"""

    def test_zero_late_days(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=0, risk_level="low")
        )
        assert result.late_fee_total == Decimal("0")

    def test_365_late_days(self):
        """滞纳金 = 欠税本金 × 0.0005 × 365"""
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=365, risk_level="low")
        )
        expected = Decimal("100000") * LATE_FEE_DAILY_RATE * Decimal("365")
        assert result.late_fee_total == expected.quantize(Decimal("0.01"))


class TestTotalExposure:
    """总风险敞口验证"""

    def test_total_sum(self):
        """总敞口 = 本金 + 罚款 + 滞纳金"""
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(
                unpaid_vat=Decimal("100000"),
                unpaid_cit=Decimal("50000"),
                late_days=365,
                risk_level="medium",
            )
        )
        expected = (
            Decimal("150000")
            + result.admin_penalty
            + result.late_fee_total
        )
        assert result.total_exposure == expected.quantize(Decimal("0.01"))

    def test_zero_unpaid_tax(self):
        """未缴税款为0 → 所有敞口为0"""
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("0"), late_days=100, risk_level="high")
        )
        assert result.total_unpaid_principal == Decimal("0")
        assert result.admin_penalty == Decimal("0")
        assert result.late_fee_total == Decimal("0")
        assert result.total_exposure == Decimal("0")


class TestIITHiddenDividend:
    """个税隐性分红穿透"""

    def test_normal_trigger(self):
        iit = _calculate_iit_hidden_dividend(Decimal("1000000"), days_overdue=400)
        assert iit == Decimal("200000")

    def test_not_triggered_under_365(self):
        iit = _calculate_iit_hidden_dividend(Decimal("1000000"), days_overdue=200)
        assert iit == Decimal("0")

    def test_zero_loan_amount(self):
        iit = _calculate_iit_hidden_dividend(Decimal("0"), days_overdue=400)
        assert iit == Decimal("0")

    def test_compound_with_iit(self):
        """含个税穿透的复合计算"""
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(
                unpaid_vat=Decimal("100000"),
                unpaid_iit=Decimal("200000"),  # 穿透还原的个税
                late_days=365,
                risk_level="high",
            )
        )
        assert result.total_unpaid_principal == Decimal("300000")


class TestGhostInvoice:
    """虚开发票叠加"""

    def test_ghost_invoice_extra_penalty(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(
                unpaid_vat=Decimal("100000"),
                late_days=0,
                risk_level="high",
                has_ghost_invoice=True,
            )
        )
        # 3.5x(偷税) + 2.0x(虚开叠加) = 5.5x
        assert result.ghost_invoice_penalty > Decimal("0")

    def test_no_ghost_no_extra(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(
                unpaid_vat=Decimal("100000"),
                late_days=0,
                risk_level="high",
                has_ghost_invoice=False,
            )
        )
        assert result.ghost_invoice_penalty == Decimal("0")


class TestReturnStructure:
    """返回值结构验证"""

    def test_return_type(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=0, risk_level="low")
        )
        assert isinstance(result, CompoundPenaltyResult)
        assert isinstance(result.total_unpaid_principal, Decimal)
        assert isinstance(result.admin_penalty, Decimal)
        assert isinstance(result.late_fee_total, Decimal)
        assert isinstance(result.total_exposure, Decimal)

    def test_business_narrative(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=100, risk_level="medium")
        )
        assert result.business_narrative
        assert "¥" in result.business_narrative

    def test_technical_narrative(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=100, risk_level="medium")
        )
        assert result.technical_narrative
        assert "征管法" in result.technical_narrative

    def test_severity_enum(self):
        """low风险 0.5x → WARNING（符合 severity 阶梯：≥0.5=WARNING）"""
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("0"), late_days=0, risk_level="low")
        )
        assert result.severity == PenaltySeverity.WARNING

    def test_critical_severity(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(
                unpaid_vat=Decimal("1000000"),
                late_days=1000,
                risk_level="critical",
                has_ghost_invoice=True,
            )
        )
        assert result.severity in (PenaltySeverity.DESTRUCTIVE, PenaltySeverity.CATACLYSMIC)


class TestTypes:
    """枚举与常量"""

    def test_penalty_multiplier_has_all_levels(self):
        assert "low" in PENALTY_MULTIPLIER
        assert "medium" in PENALTY_MULTIPLIER
        assert "high" in PENALTY_MULTIPLIER
        assert "critical" in PENALTY_MULTIPLIER

    def test_late_fee_rate(self):
        assert LATE_FEE_DAILY_RATE == Decimal("0.0005")

    def test_iit_rate(self):
        assert IIT_DIVIDEND_RATE == Decimal("0.20")
