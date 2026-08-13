"""
tax_risk_engine 单元测试

覆盖五维引擎的核心函数：
  - _assess_macro_internal_control：重/轻资产分支、成本费用率内控崩溃异常
  - _assess_vat_gaar：合同-发票偏离、资金闭环回流、无形资产转让定价
  - _assess_iit_hidden_dividend：股东借款 365 天穿透
  - calculate_comprehensive_tax_risk：五维主流程、内控失败写库、GAAR 捕获、一票否决
  - _generate_comprehensive_narrative：双语报告生成
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.tax_risk_engine import (
    EnterpriseDataPayload,
    ComprehensiveTaxRiskResult,
    InternalControlFailureWarning,
    GAARViolationWarning,
    _assess_macro_internal_control,
    _assess_vat_gaar,
    _assess_iit_hidden_dividend,
    calculate_comprehensive_tax_risk,
    _generate_comprehensive_narrative,
)


def _payload(**overrides) -> EnterpriseDataPayload:
    p = EnterpriseDataPayload(
        enterprise_id="ent-1",
        enterprise_name="测试企业",
        industry="制造",
        revenue_annual=Decimal("10000000"),
        total_cost=Decimal("6000000"),
        total_expenses=Decimal("1000000"),
        net_profit=Decimal("3000000"),
        total_assets=Decimal("5000000"),
        asset_type="heavy_asset",
        depreciation_amount=Decimal("50000"),
        depreciation_to_revenue_ratio=Decimal("0.01"),
        max_cost_expense_ratio=Decimal("0.70"),
        output_invoice_total=Decimal("1000000"),
        input_invoice_total=Decimal("800000"),
        declared_tax=Decimal("200000"),
        actual_paid=Decimal("180000"),
    )
    for key, value in overrides.items():
        setattr(p, key, value)
    return p


# ═══════════════════════════════════════════
# 维度一：异质性宏观内控
# ═══════════════════════════════════════════

class TestMacroInternalControl:
    def test_heavy_asset_depreciation_flag(self):
        """重资产折旧/营收比超过警戒线 → 产生风险标记与评分"""
        payload = _payload(
            asset_type="heavy_asset",
            depreciation_amount=Decimal("2000000"),  # 0.2 > 0.01
        )
        score, flags, recs, tech = _assess_macro_internal_control(payload)
        assert score == 25.0
        assert len(flags) == 1
        assert "折旧营收比" in flags[0]
        assert tech["depreciation_check"]["violation"] is True

    def test_heavy_asset_depreciation_below_threshold(self):
        """折旧占比正常 → 无标记"""
        payload = _payload(asset_type="heavy_asset")
        score, flags, recs, tech = _assess_macro_internal_control(payload)
        assert score == 0.0
        assert flags == []
        assert tech["depreciation_check"]["violation"] is False

    def test_heavy_asset_no_revenue_skips_checks(self):
        """无营收 → 折旧与成本费用检查均跳过"""
        payload = _payload(asset_type="heavy_asset", revenue_annual=Decimal("0"))
        score, flags, _, tech = _assess_macro_internal_control(payload)
        assert score == 0.0
        assert flags == []
        assert tech["cost_expense_ratio_check"] == {}

    def test_light_asset_intangible_flag(self):
        """轻资产无形摊销占总成本 >10% → 标记"""
        payload = _payload(
            asset_type="light_asset",
            intangible_amortization=Decimal("1000000"),  # 1/6 ≈ 16.7% > 10%
        )
        score, flags, recs, tech = _assess_macro_internal_control(payload)
        assert score == 25.0
        assert any("无形资产摊销" in f for f in flags)
        assert tech["violation_count"] == 1

    def test_light_asset_service_fee_flag(self):
        """服务费占营收 >30% → 标记费用化冲账嫌疑"""
        payload = _payload(
            asset_type="light_asset",
            service_fee_total=Decimal("4000000"),  # 40% > 30%
        )
        score, flags, _, _ = _assess_macro_internal_control(payload)
        assert score == 25.0
        assert any("费用化冲账" in f for f in flags)

    def test_light_asset_both_flags_score_50(self):
        """无形摊销+服务费同时触发 → 评分 50"""
        payload = _payload(
            asset_type="light_asset",
            intangible_amortization=Decimal("1000000"),
            service_fee_total=Decimal("4000000"),
        )
        score, flags, _, _ = _assess_macro_internal_control(payload)
        assert score == 50.0
        assert len(flags) == 2

    def test_light_asset_clean(self):
        """轻资产各项指标正常 → 无标记"""
        payload = _payload(
            asset_type="light_asset",
            intangible_amortization=Decimal("100000"),
            service_fee_total=Decimal("1000000"),
        )
        score, flags, _, _ = _assess_macro_internal_control(payload)
        assert score == 0.0
        assert flags == []

    def test_cost_expense_ratio_raises_warning(self):
        """成本费用率 > 基准×1.5 → 抛 InternalControlFailureWarning"""
        payload = _payload(
            total_cost=Decimal("9000000"),
            total_expenses=Decimal("3000000"),  # 1.2 > 0.7*1.5=1.05
        )
        with pytest.raises(InternalControlFailureWarning) as exc:
            _assess_macro_internal_control(payload)
        assert exc.value.enterprise_name == "测试企业"
        assert "成本费用率" in exc.value.reason

    def test_cost_expense_ratio_within_threshold(self):
        """成本费用率正常 → 不抛异常"""
        payload = _payload()
        score, flags, _, tech = _assess_macro_internal_control(payload)
        assert score == 0.0
        assert tech["cost_expense_ratio_check"]["actual_ratio"] == str(Decimal("0.7000"))


# ═══════════════════════════════════════════
# 维度二：增值税 GAAR 反避税
# ═══════════════════════════════════════════

class TestVatGaar:
    def test_no_contracts_clean(self):
        score, flags, recs, violations = _assess_vat_gaar(_payload(contracts=[]))
        assert score == 0.0
        assert flags == []
        assert violations == []

    def test_contract_invoice_deviation_flag(self):
        """合同金额与发票总额偏离 >30% → 标记"""
        payload = _payload(contracts=[{
            "contract_no": "HT1", "counterparty": "甲客户",
            "contract_amount": 1000, "product_name": "设备",
        }])
        score, flags, _, _ = _assess_vat_gaar(payload)
        assert score == 20.0
        assert any("偏离" in f for f in flags)

    def test_contract_invoice_deviation_small_no_flag(self):
        """偏离 ≤30% → 无标记"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "设备",
            }],
            invoices=[{
                "invoice_no": "FP1", "buyer_name": "甲客户",
                "total_amount": 1050,
            }],
        )
        score, flags, _, _ = _assess_vat_gaar(payload)
        assert score == 0.0
        assert flags == []

    def test_capital_loopback_raises_warning(self):
        """30 天内资金闭环回流 → 抛 GAARViolationWarning"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "设备",
            }],
            bank_transactions=[
                {"counterparty": "甲客户", "amount": 100,
                 "transaction_date": "2026-01-01", "direction": "outflow"},
                {"counterparty": "甲客户", "amount": 105,
                 "transaction_date": "2026-01-20", "direction": "inflow"},
            ],
        )
        with pytest.raises(GAARViolationWarning) as exc:
            _assess_vat_gaar(payload)
        assert exc.value.violation_type == "capital_loopback"

    def test_capital_loopback_over_30_days_no_warning(self):
        """回流超过 30 天 → 不构成闭环回流"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "设备",
            }],
            bank_transactions=[
                {"counterparty": "甲客户", "amount": 100,
                 "transaction_date": "2026-01-01", "direction": "outflow"},
                {"counterparty": "甲客户", "amount": 105,
                 "transaction_date": "2026-03-05", "direction": "inflow"},
            ],
        )
        _assess_vat_gaar(payload)  # 不应抛异常

    def test_capital_loopback_return_ratio_too_large(self):
        """回流金额偏差 ≥10% → 不构成闭环回流"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "设备",
            }],
            bank_transactions=[
                {"counterparty": "甲客户", "amount": 100,
                 "transaction_date": "2026-01-01", "direction": "outflow"},
                {"counterparty": "甲客户", "amount": 130,
                 "transaction_date": "2026-01-20", "direction": "inflow"},
            ],
        )
        _assess_vat_gaar(payload)  # return_ratio=0.3 ≥ 0.10，不应抛异常

    def test_invalid_transaction_date_skipped(self):
        """日期解析失败 → 静默跳过回流检测"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "设备",
            }],
            bank_transactions=[
                {"counterparty": "甲客户", "amount": 100,
                 "transaction_date": "not-a-date", "direction": "outflow"},
                {"counterparty": "甲客户", "amount": 105,
                 "transaction_date": "2026-01-20", "direction": "inflow"},
            ],
        )
        _assess_vat_gaar(payload)  # 不应抛异常

    def test_intangible_transfer_pricing_abuse(self):
        """无形资产转让定价畸低（<30%）→ 追加违规与整改建议"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "无形资产专利",
            }],
            invoices=[{
                "invoice_no": "FP1", "buyer_name": "甲客户",
                "total_amount": 10000,
            }],
        )
        score, flags, recs, violations = _assess_vat_gaar(payload)
        assert any(v["type"] == "transfer_pricing_abuse" for v in violations)
        assert any("转让定价" in r for r in recs)
        assert score == 55.0  # 2 flags*20 + 1 violation*15

    def test_intangible_pricing_fair_no_violation(self):
        """无形资产定价合理 → 无违规"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 5000, "product_name": "软件许可",
            }],
            invoices=[{
                "invoice_no": "FP1", "buyer_name": "甲客户",
                "total_amount": 10000,
            }],
        )
        _, flags, _, violations = _assess_vat_gaar(payload)
        assert violations == []
        assert any("偏离" in f for f in flags)  # 金额偏离仍标记

    def test_score_capped_at_100(self):
        """多笔偏离 → 评分封顶 100"""
        payload = _payload(contracts=[
            {"contract_no": f"HT{i}", "counterparty": f"客户{i}",
             "contract_amount": 1000, "product_name": "设备"}
            for i in range(6)
        ])
        score, flags, _, _ = _assess_vat_gaar(payload)
        assert score == 100.0
        assert len(flags) == 6


# ═══════════════════════════════════════════
# 维度三：个税隐性分红穿透
# ═══════════════════════════════════════════

class TestIitHiddenDividend:
    def test_no_receivables(self):
        score, flags, _, amount, detail = _assess_iit_hidden_dividend(_payload())
        assert score == 0.0
        assert flags == []
        assert amount == Decimal("0")
        assert detail == "no_shareholder_loans_triggered"

    def test_non_shareholder_relation_skipped(self):
        payload = _payload(other_receivables=[{
            "borrower": "张三", "relation": "员工借款",
            "amount": 100000, "loan_date": date.today() - timedelta(days=400),
        }])
        score, flags, _, amount, _ = _assess_iit_hidden_dividend(payload)
        assert score == 0.0
        assert amount == Decimal("0")

    def test_loan_under_365_days_skipped(self):
        payload = _payload(other_receivables=[{
            "borrower": "李四", "relation": "股东",
            "amount": 100000, "loan_date": date.today() - timedelta(days=300),
        }])
        score, flags, _, amount, _ = _assess_iit_hidden_dividend(payload)
        assert score == 0.0
        assert amount == Decimal("0")

    def test_shareholder_loan_over_365_days_triggered(self):
        payload = _payload(other_receivables=[{
            "borrower": "王五", "relation": "股东",
            "amount": 100000, "loan_date": date.today() - timedelta(days=400),
        }])
        score, flags, recs, amount, detail = _assess_iit_hidden_dividend(payload)
        assert amount == Decimal("20000.00")  # 100000 * 20%
        assert score == 20.0
        assert any("158号" in f for f in flags)
        assert recs

    def test_only_overdue_loans_summed(self):
        """仅逾期满 365 天的股东借款参与穿透"""
        payload = _payload(other_receivables=[
            {"borrower": "王五", "relation": "股东", "amount": 100000,
             "loan_date": date.today() - timedelta(days=400)},
            {"borrower": "供应商A", "relation": "供应商", "amount": 50000,
             "loan_date": date.today() - timedelta(days=100)},
        ])
        _, _, _, amount, _ = _assess_iit_hidden_dividend(payload)
        assert amount == Decimal("20000.00")

    def test_invalid_loan_date_skipped(self):
        payload = _payload(other_receivables=[{
            "borrower": "王五", "relation": "股东",
            "amount": 100000, "loan_date": "not-a-date",
        }])
        score, _, _, amount, _ = _assess_iit_hidden_dividend(payload)
        assert score == 0.0
        assert amount == Decimal("0")

    def test_loan_date_as_date_object(self):
        payload = _payload(other_receivables=[{
            "borrower": "赵六", "relation": "直系亲属",
            "amount": 50000, "loan_date": date.today() - timedelta(days=500),
        }])
        _, _, _, amount, _ = _assess_iit_hidden_dividend(payload)
        assert amount == Decimal("10000.00")

    def test_score_capped_at_100(self):
        payload = _payload(other_receivables=[{
            "borrower": "王五", "relation": "股东",
            "amount": 20000000, "loan_date": date.today() - timedelta(days=400),
        }])
        score, _, _, _, _ = _assess_iit_hidden_dividend(payload)
        assert score == 100.0


# ═══════════════════════════════════════════
# 五维全景主流程
# ═══════════════════════════════════════════

class _RecordingDB:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def commit(self):
        self.commits += 1


class TestComprehensiveRisk:
    @pytest.mark.asyncio
    async def test_normal_path_low_risk(self):
        """干净载荷 → 五个维度、低风险、生成叙述"""
        db = _RecordingDB()
        result = await calculate_comprehensive_tax_risk("ent-1", _payload(), db)
        assert isinstance(result, ComprehensiveTaxRiskResult)
        assert set(result.dimension_scores.keys()) == {
            "macro_internal_control", "vat_gaar", "iit_hidden_dividend",
            "compound_penalty", "four_flow_match",
        }
        assert result.overall_risk_level == "low"
        assert result.overall_risk_score < 30
        assert result.compound_penalty is not None
        assert "测试企业" in result.business_narrative
        assert result.technical_summary["dimension_scores"]["vat_gaar"] == 0.0
        assert db.executed == []  # 正常路径不写库

    @pytest.mark.asyncio
    async def test_internal_control_failure_writes_db(self):
        """内控崩溃 → 写回 Enterprise 表并标记 critical"""
        db = _RecordingDB()
        payload = _payload(
            total_cost=Decimal("9000000"),
            total_expenses=Decimal("3000000"),
        )
        result = await calculate_comprehensive_tax_risk("ent-1", payload, db)
        assert result.is_internal_control_failed is True
        assert result.overall_risk_level == "critical"
        assert result.overall_risk_score == 100.0
        assert len(db.executed) == 1
        assert db.commits == 1
        assert result.technical_summary["status"] == "internal_control_failed"

    @pytest.mark.asyncio
    async def test_gaar_violation_does_not_abort(self):
        """GAAR 违规 → 维度二记 100 分但评估继续"""
        payload = _payload(
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "设备",
            }],
            bank_transactions=[
                {"counterparty": "甲客户", "amount": 100,
                 "transaction_date": "2026-01-01", "direction": "outflow"},
                {"counterparty": "甲客户", "amount": 105,
                 "transaction_date": "2026-01-20", "direction": "inflow"},
            ],
        )
        result = await calculate_comprehensive_tax_risk("ent-1", payload, _RecordingDB())
        assert result.dimension_scores["vat_gaar"] == 100.0
        assert any(v["type"] == "capital_loopback" for v in result.gaar_violations)
        assert result.dimension_scores["four_flow_match"] >= 0

    @pytest.mark.asyncio
    async def test_veto_rules_escalate_to_critical(self):
        """≥3 个维度高分 → 一票否决升级为 critical"""
        payload = _payload(
            asset_type="light_asset",
            other_receivables=[{
                "borrower": "王五", "relation": "股东",
                "amount": 20000000, "loan_date": date.today() - timedelta(days=400),
            }],
            contracts=[{
                "contract_no": "HT1", "counterparty": "甲客户",
                "contract_amount": 1000, "product_name": "设备",
            }],
            bank_transactions=[
                {"counterparty": "甲客户", "amount": 100,
                 "transaction_date": "2026-01-01", "direction": "outflow"},
                {"counterparty": "甲客户", "amount": 105,
                 "transaction_date": "2026-01-20", "direction": "inflow"},
            ],
        )
        result = await calculate_comprehensive_tax_risk("ent-1", payload, _RecordingDB())
        assert result.overall_risk_level == "critical"
        assert result.overall_risk_score == 80.0
        assert result.technical_summary["veto_triggered"] is True
        assert result.dimension_scores["iit_hidden_dividend"] == 100.0

    @pytest.mark.asyncio
    async def test_all_dims_carry_policy_fields(self):
        """五个维度详情均携带 risk_reason / policy_ref / policy_basis"""
        result = await calculate_comprehensive_tax_risk("ent-1", _payload(), _RecordingDB())
        expected_dims = [
            "macro_internal_control", "vat_gaar", "iit_hidden_dividend",
            "compound_penalty", "four_flow_match",
        ]
        for dim in expected_dims:
            assert dim in result.dim_details, f"缺少维度: {dim}"
            detail = result.dim_details[dim]
            assert "risk_reason" in detail, f"{dim} 缺少 risk_reason"
            assert "policy_ref" in detail, f"{dim} 缺少 policy_ref"
            assert "policy_basis" in detail, f"{dim} 缺少 policy_basis"
            assert isinstance(detail["policy_ref"], str) and detail["policy_ref"], \
                f"{dim} 的 policy_ref 为空"
            assert isinstance(detail["policy_basis"], str) and detail["policy_basis"], \
                f"{dim} 的 policy_basis 为空"


# ═══════════════════════════════════════════
# 双语叙述生成
# ═══════════════════════════════════════════

class TestNarrative:
    def test_narrative_contains_key_sections(self):
        result = ComprehensiveTaxRiskResult(
            enterprise_id="ent-1",
            enterprise_name="测试企业",
            assessment_date="2026-08-13T00:00:00+00:00",
            overall_risk_level="high",
            overall_risk_score=66.6,
            dimension_scores={"macro_internal_control": 0.0, "vat_gaar": 100.0},
            dim_details={"vat_gaar": {"detail": "增值税一般反避税规则审查"}},
        )
        narrative = _generate_comprehensive_narrative(result, _payload())
        assert "测试企业" in narrative
        assert "综合风险等级" in narrative
        assert "高风险 · 红色预警" in narrative
        assert "增值税 GAAR 反避税审查" in narrative

    def test_narrative_low_risk_and_penalty_breakdown(self):
        result = ComprehensiveTaxRiskResult(
            enterprise_name="测试企业",
            overall_risk_level="low",
            overall_risk_score=5.0,
            dimension_scores={"macro_internal_control": 0.0, "vat_gaar": 0.0},
        )
        result.risk_flags = []
        narrative = _generate_comprehensive_narrative(result, _payload())
        assert "未发现重大财税合规风险" in narrative
        assert "低风险 · 绿色通行" in narrative
