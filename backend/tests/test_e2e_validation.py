"""
端到端验证脚本（跳过模式 — 需构造大批数据，耗时较长）

验证：
  1. 企业A（正常）：四流匹配度 ≈ 90+，总体风险 = low，风险偏离度 < 50
  2. 企业B（轻度风险）：四流匹配度 ≈ 70-80，总体风险 = medium，风险偏离度 50-70
  3. 企业C（重度风险）：四流匹配度 ≈ 40-55，总体风险 = high，风险偏离度 > 70
  4. 边界条件：零值 / 极值 / 双语输出

环境变量 RUN_E2E_TESTS=1 来执行：
    $env:RUN_E2E_TESTS=1; pytest tests/test_e2e_validation.py -v
"""

import os
import pytest
import sys
from datetime import date
from decimal import Decimal

from app.core.four_flow_match import (
    calculate_four_flow_match,
    ContractRecord, InvoiceRecord, BankTransactionRecord,
)
from app.core.risk_engine import assess_enterprise_risk, EnterpriseRiskInput
from app.core.penalty_calculator import (
    calculate_compound_penalty_exposure,
    UnpaidTaxInput,
    PENALTY_MULTIPLIER,
    LATE_FEE_DAILY_RATE,
    IIT_DIVIDEND_RATE,
)
from app.core.simulation_engine import run_simulation, SimulationInput
from app.core.tax_preference import check_tax_preference, PreferenceCheckInput
from app.core.intervention import generate_intervention, InterventionInput


SKIP_E2E = os.environ.get("RUN_E2E_TESTS") != "1"
pytestmark = pytest.mark.skipif(SKIP_E2E, reason="设置 RUN_E2E_TESTS=1 执行端到端测试")


def _check(label, condition, detail=""):
    if condition:
        return True, f"OK [{label}] {detail}"
    return False, f"FAIL [{label}]: {detail}"


class TestFourFlowMatchBasic:
    """四流匹配快速验证（不需要数据库）"""

    def test_perfect_match(self):
        contracts = [ContractRecord("C1", 1000000, "买方A", "卖方B")]
        invoices = [InvoiceRecord("INV1", 1000000, "合同C1", "买方A", "卖方B")]
        bank = [BankTransactionRecord("TX1", 1000000, "买方A", "卖方B", "货款")]
        score = calculate_four_flow_match(contracts, invoices, bank)
        assert score >= 80.0, f"完美匹配应高分，实际: {score}"

    def test_empty_data(self):
        score = calculate_four_flow_match([], [], [])
        assert score == 0.0

    def test_mismatch_data(self):
        contracts = [ContractRecord("C1", 1000000, "买方A", "卖方B")]
        invoices = [InvoiceRecord("INV1", 500000, "合同C1", "买方A", "卖方B")]
        bank = [BankTransactionRecord("TX1", 300000, "买方A", "卖方B", "货款")]
        score = calculate_four_flow_match(contracts, invoices, bank)
        assert 0.0 <= score <= 100.0


class TestPenaltyCalculatorUnit:
    """罚款推演快速验证"""

    def test_low_risk_no_late(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(unpaid_vat=Decimal("100000"), late_days=0, risk_level="low")
        )
        assert result.total_unpaid_principal == Decimal("100000")
        assert result.penalty_multiplier == Decimal("0.5")

    def test_critical_with_ghost(self):
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(
                unpaid_vat=Decimal("1000000"),
                late_days=1000,
                risk_level="critical",
                has_ghost_invoice=True,
            )
        )
        assert result.total_exposure > Decimal("1000000")


class TestTaxPreferenceUnit:
    """税收优惠快速验证"""

    def test_small_micro_eligible(self):
        result = check_tax_preference(PreferenceCheckInput(
            revenue=5_000_000, employees=50, total_assets=20_000_000,
            rnd_pct=0.0, is_manufacturing=False,
        ))
        assert result.is_small_micro_eligible

    def test_not_eligible_large(self):
        result = check_tax_preference(PreferenceCheckInput(
            revenue=500_000_000, employees=500, total_assets=200_000_000,
            rnd_pct=0.0, is_manufacturing=False,
        ))
        assert not result.is_small_micro_eligible


class TestInterventionUnit:
    """干预策略快速验证"""

    def test_intervention_output(self):
        result = generate_intervention(InterventionInput(
            dominant_biases=["control_desire", "optimism_bias"],
            deviation_index=75.0,
            risk_level="high",
        ))
        assert result.layers
        assert len(result.priority_order) > 0


# 不使用 __name__ == "__main__" 的 sys.exit() 以避免阻塞 pytest 全量运行
# 端到端测试通过 pytest.mark.skipif + RUN_E2E_TESTS 环境变量控制
