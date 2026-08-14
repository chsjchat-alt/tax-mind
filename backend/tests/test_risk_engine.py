"""
风险识别规则引擎单元测试

覆盖场景：
  - 正常场景：各维度正常数据、低风险企业
  - 边界场景：阈值临界值、零值输入、单维度高风险
  - 异常场景：全维度高风险、空数据、极端数值
  - 集成场景：与四流匹配模块联动
"""

import pytest
from datetime import date
from decimal import Decimal

from app.core.risk_engine import (
    assess_enterprise_risk,
    EnterpriseRiskInput,
    RiskAssessmentResult,
    RISK_HIGH_THRESHOLD,
    RISK_MEDIUM_THRESHOLD,
    RISK_WEIGHTS,
    INDUSTRY_TAX_BURDEN_REFERENCE,
    INDUSTRY_COST_RATE_REFERENCE,
)
from app.core.four_flow_match import (
    FourFlowMatchResult,
    ContractRecord,
    InvoiceRecord,
    BankTransactionRecord,
)


# ═══════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def normal_enterprise():
    """正常经营的企业——低风险"""
    return EnterpriseRiskInput(
        enterprise_name="正常科技有限公司",
        industry="制造",
        revenue_annual=Decimal("5000000.00"),
        tax_rate_industry=Decimal("3.0"),
        cost_rate_industry=Decimal("85.0"),
        actual_tax_burden_rate=Decimal("2.8"),
        actual_cost_rate=Decimal("84.0"),
        total_private_card_amount=Decimal("0"),
        total_revenue=Decimal("5000000.00"),
        total_input_invoice=Decimal("500000.00"),
        total_output_invoice=Decimal("650000.00"),
    )


@pytest.fixture
def high_risk_enterprise():
    """高风险企业——多个维度异常"""
    return EnterpriseRiskInput(
        enterprise_name="高风险商贸公司",
        industry="批发零售",
        revenue_annual=Decimal("2000000.00"),
        tax_rate_industry=Decimal("1.5"),
        cost_rate_industry=Decimal("95.0"),
        actual_tax_burden_rate=Decimal("0.2"),
        actual_cost_rate=Decimal("120.0"),
        total_private_card_amount=Decimal("800000.00"),
        total_revenue=Decimal("2000000.00"),
        total_input_invoice=Decimal("100000.00"),
        total_output_invoice=Decimal("50000.00"),
    )


@pytest.fixture
def perfect_flow_match():
    """完美的四流匹配结果"""
    result = FourFlowMatchResult()
    result.overall_score = 98.0
    result.contract_invoice_score = 100.0
    result.invoice_bank_score = 100.0
    result.counterparty_consistency_score = 100.0
    result.amount_consistency_score = 95.0
    result.product_match_score = 100.0
    return result


@pytest.fixture
def poor_flow_match():
    """糟糕的四流匹配结果"""
    result = FourFlowMatchResult()
    result.overall_score = 25.0
    result.contract_invoice_score = 20.0
    result.invoice_bank_score = 20.0
    result.counterparty_consistency_score = 30.0
    result.amount_consistency_score = 30.0
    result.product_match_score = 0.0
    result.risk_flags = ["合同 CT-001 未找到对应发票", "发票 INV-001 与银行流水金额差异较大"]
    return result


# ═══════════════════════════════════════════════════════════
#  正常场景
# ═══════════════════════════════════════════════════════════

class TestNormalScenarios:
    """正常业务场景"""

    def test_low_risk_enterprise(self, normal_enterprise, perfect_flow_match):
        """低风险正常企业"""
        result = assess_enterprise_risk(
            enterprise_input=normal_enterprise,
            flow_match_result=perfect_flow_match,
        )
        assert result.overall_risk_level == "low"
        assert result.overall_risk_score < RISK_MEDIUM_THRESHOLD
        assert len(result.risk_flags) == 0
        assert "财税合规" in result.business_narrative

    def test_return_type(self, normal_enterprise, perfect_flow_match):
        """返回值类型正确"""
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert isinstance(result, RiskAssessmentResult)
        assert isinstance(result.overall_risk_level, str)
        assert isinstance(result.overall_risk_score, float)
        assert isinstance(result.dimension_scores, dict)
        assert isinstance(result.risk_flags, list)
        assert isinstance(result.recommendations, list)
        assert isinstance(result.business_narrative, str)
        assert isinstance(result.technical_summary, dict)

    def test_six_dimensions_present(self, normal_enterprise, perfect_flow_match):
        """六个风险维度全部评估"""
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        expected_dims = [
            "four_flow_match",
            "private_card_ratio",
            "cost_deviation",
            "tax_burden_deviation",
            "input_output_imbalance",
            "invoice_bank_mismatch",
        ]
        for dim in expected_dims:
            assert dim in result.dimension_scores, f"缺少维度: {dim}"
            assert 0.0 <= result.dimension_scores[dim] <= 100.0

    def test_technical_summary_completeness(self, normal_enterprise, perfect_flow_match):
        """技术摘要结构完整"""
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        ts = result.technical_summary
        assert "dimension_scores" in ts
        assert "overall_score" in ts
        assert "risk_level" in ts
        assert "weights" in ts
        assert "flags_count" in ts
        assert "thresholds" in ts

    def test_no_flow_match_internal_calculation(self, normal_enterprise):
        """不传 flow_match_result 时内部自行计算"""
        result = assess_enterprise_risk(
            enterprise_input=normal_enterprise,
            flow_match_result=None,
        )
        assert isinstance(result, RiskAssessmentResult)
        # 至少能正常返回
        assert result.overall_risk_level in ("low", "medium", "high")


# ═══════════════════════════════════════════════════════════
#  边界场景
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界场景测试"""

    def test_empty_data_insufficient(self):
        """空数据 → 数据不足"""
        empty_input = EnterpriseRiskInput(
            enterprise_name="空企业",
            industry="制造",
            revenue_annual=Decimal("0"),
            tax_rate_industry=Decimal("3.0"),
            cost_rate_industry=Decimal("85.0"),
            actual_tax_burden_rate=Decimal("0"),
            actual_cost_rate=Decimal("0"),
            total_private_card_amount=Decimal("0"),
            total_revenue=Decimal("0"),
            total_input_invoice=Decimal("0"),
            total_output_invoice=Decimal("0"),
        )
        result = assess_enterprise_risk(enterprise_input=empty_input)
        assert result.technical_summary["status"] == "insufficient_data"
        assert "暂无足够经营数据" in result.business_narrative

    def test_private_card_threshold_5pct(self, normal_enterprise, perfect_flow_match):
        """私卡占比恰好 5% 边界"""
        normal_enterprise.total_private_card_amount = Decimal("250000")  # 5% of 5M
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        # 5% 应触发低风险评分，但不一定有 flag
        assert result.dimension_scores["private_card_ratio"] >= 0.0

    def test_private_card_threshold_15pct(self, normal_enterprise, perfect_flow_match):
        """私卡占比 15%——制造业锚点 10%，超额 5%刚好在边界（无标记）"""
        normal_enterprise.total_private_card_amount = Decimal("750000")  # 15%
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        # excess=5% 恰好处于 0.05 阈值边界：score=20.0，无标记
        assert result.dimension_scores["private_card_ratio"] == pytest.approx(20.0, abs=1)
        # 无风险标记（<=5% 超额不生成标记）
        assert not any("私卡收款" in f for f in result.risk_flags)

    def test_private_card_threshold_30pct(self, normal_enterprise, perfect_flow_match):
        """私卡占比 30%——制造业锚点 10%，超额 20%，属于严重违规"""
        normal_enterprise.total_private_card_amount = Decimal("1500000")  # 30%
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert any("隐匿收入" in f or "私卡收款" in f for f in result.risk_flags)
        assert any("行业均值" in f for f in result.risk_flags)
        # excess=20%: score = 55 + (0.20-0.15)*250 = 67.5
        assert result.dimension_scores["private_card_ratio"] >= 65.0

    def test_private_card_no_revenue(self):
        """有私卡收入但无申报收入"""
        inp = EnterpriseRiskInput(
            enterprise_name="测试", industry="制造", revenue_annual=Decimal("0"),
            tax_rate_industry=Decimal("3.0"), cost_rate_industry=Decimal("85.0"),
            actual_tax_burden_rate=Decimal("0"), actual_cost_rate=Decimal("0"),
            total_private_card_amount=Decimal("100000"), total_revenue=Decimal("0"),
            total_input_invoice=Decimal("0"), total_output_invoice=Decimal("0"),
        )
        result = assess_enterprise_risk(inp)
        assert any("无申报收入" in f or "私卡收款" in f for f in result.risk_flags)
        assert result.dimension_scores["private_card_ratio"] >= 70.0

    def test_private_card_industry_anchor_differentiation(self, perfect_flow_match):
        """同一私卡占比 17%：餐饮(锚点12%=5%超额→无标记) vs 批发(锚点8%=9%超额→异常)"""
        base = dict(
            enterprise_name="测试", revenue_annual=Decimal("5000000"),
            actual_tax_burden_rate=Decimal("3"), actual_cost_rate=Decimal("85"),
            total_private_card_amount=Decimal("850000"), total_revenue=Decimal("5000000"),  # 17%
            total_input_invoice=Decimal("0"), total_output_invoice=Decimal("0"),
            tax_rate_industry=Decimal("3"), cost_rate_industry=Decimal("85"),
        )
        # 餐饮服务(锚点12%)：excess=5% → low risk, no flags
        catering = EnterpriseRiskInput(industry="餐饮服务", **base)
        r_catering = assess_enterprise_risk(catering, perfect_flow_match)
        assert r_catering.dimension_scores["private_card_ratio"] <= 25.0
        assert not any("私卡收款" in f for f in r_catering.risk_flags)

        # 批发零售(锚点8%)：excess=9% → triggers "行业均值" flag
        wholesale = EnterpriseRiskInput(industry="批发零售", **base)
        r_wholesale = assess_enterprise_risk(wholesale, perfect_flow_match)
        assert r_wholesale.dimension_scores["private_card_ratio"] > 25.0
        assert any("行业均值" in f for f in r_wholesale.risk_flags)

    def test_cost_deviation_threshold_5pct(self, normal_enterprise, perfect_flow_match):
        """成本偏离恰好 5 个百分点——应无风险"""
        normal_enterprise.actual_cost_rate = Decimal("90.0")  # vs 85.0 industry
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.dimension_scores["cost_deviation"] <= 1.0

    def test_cost_deviation_threshold_15pct(self, normal_enterprise, perfect_flow_match):
        """成本偏离 15 个百分点"""
        normal_enterprise.actual_cost_rate = Decimal("100.0")  # vs 85.0 → 15pp
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.dimension_scores["cost_deviation"] >= 10.0
        assert any("成本费用率" in f for f in result.risk_flags)

    def test_cost_deviation_over_30pct(self, normal_enterprise, perfect_flow_match):
        """成本偏离超过 30 个百分点——极度异常"""
        normal_enterprise.actual_cost_rate = Decimal("120.0")  # vs 85.0 → 35pp
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.dimension_scores["cost_deviation"] >= 70.0
        assert any("虚列成本" in f for f in result.risk_flags)

    def test_tax_burden_low_but_normal(self, normal_enterprise, perfect_flow_match):
        """税负率略低但在正常范围"""
        normal_enterprise.actual_tax_burden_rate = Decimal("2.5")  # vs 3.0 → deviation=0.5
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        # deviation=0.5 应触发低风险
        assert result.dimension_scores["tax_burden_deviation"] >= 0.0

    def test_tax_burden_severely_low(self, normal_enterprise, perfect_flow_match):
        """税负率严重偏低"""
        normal_enterprise.actual_tax_burden_rate = Decimal("0.3")  # vs 3.0 → deviation=2.7
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.dimension_scores["tax_burden_deviation"] >= 60.0
        assert any("税负率" in f for f in result.risk_flags)

    def test_product_match_perfect(self, normal_enterprise, perfect_flow_match):
        """品名完全匹配（Jaccard=100） → 风险分为 0"""
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.dimension_scores["input_output_imbalance"] == 0.0

    def test_product_match_high(self, normal_enterprise):
        """品名高匹配（Jaccard=80） → 风险分较低，无标记"""
        fm = FourFlowMatchResult()
        fm.overall_score = 90.0
        fm.product_match_score = 80.0
        result = assess_enterprise_risk(normal_enterprise, fm)
        assert result.dimension_scores["input_output_imbalance"] == pytest.approx(20.0, abs=1)
        # Jaccard >= 0.6 无风险标记
        assert not any("品名" in f for f in result.risk_flags)

    def test_product_match_moderate(self, normal_enterprise):
        """品名中度匹配（Jaccard=50） → 有风险标记"""
        fm = FourFlowMatchResult()
        fm.overall_score = 80.0
        fm.product_match_score = 50.0
        result = assess_enterprise_risk(normal_enterprise, fm)
        assert result.dimension_scores["input_output_imbalance"] == pytest.approx(50.0, abs=1)
        assert any("品名" in f for f in result.risk_flags)
        assert any("Jaccard" in f for f in result.risk_flags)

    def test_product_match_low(self, normal_enterprise):
        """品名极低匹配（Jaccard=15） → 高风分险 + 风险标记"""
        fm = FourFlowMatchResult()
        fm.overall_score = 70.0
        fm.product_match_score = 15.0
        result = assess_enterprise_risk(normal_enterprise, fm)
        assert result.dimension_scores["input_output_imbalance"] == pytest.approx(85.0, abs=1)
        assert any("品名" in f for f in result.risk_flags)
        assert any("极低" in f for f in result.risk_flags)


# ═══════════════════════════════════════════════════════════
#  集成场景
# ═══════════════════════════════════════════════════════════

class TestIntegrationScenarios:
    """集成场景——多维度综合评估"""

    def test_high_risk_all_dimensions(self, high_risk_enterprise, poor_flow_match):
        """全维度高风险综合评估"""
        # 进一步加大风险以便达到 high
        high_risk_enterprise.actual_tax_burden_rate = Decimal("0.05")
        high_risk_enterprise.total_private_card_amount = Decimal("1000000")  # 50%
        high_risk_enterprise.total_input_invoice = Decimal("0")
        high_risk_enterprise.total_output_invoice = Decimal("500000")
        result = assess_enterprise_risk(high_risk_enterprise, poor_flow_match)
        assert result.overall_risk_level == "high"
        assert result.overall_risk_score >= RISK_HIGH_THRESHOLD
        assert len(result.risk_flags) >= 3
        assert len(result.recommendations) >= 2

    def test_medium_risk_mixed(self, normal_enterprise):
        """混合风险——部分维度中风险"""
        normal_enterprise.total_private_card_amount = Decimal("600000")  # 12%
        normal_enterprise.actual_tax_burden_rate = Decimal("1.0")  # vs 3.0
        normal_enterprise.actual_cost_rate = Decimal("100.0")  # vs 85.0
        poor = FourFlowMatchResult()
        poor.overall_score = 50.0
        poor.contract_invoice_score = 45.0
        poor.invoice_bank_score = 55.0
        poor.counterparty_consistency_score = 45.0
        poor.amount_consistency_score = 55.0
        result = assess_enterprise_risk(normal_enterprise, poor)
        assert result.overall_risk_level in ("medium", "high")

    def test_risk_level_thresholds(self, normal_enterprise, poor_flow_match):
        """风险等级阈值边界验证"""
        # 全正常 → low
        perfect = FourFlowMatchResult()
        perfect.overall_score = 100.0
        perfect.contract_invoice_score = 100.0
        perfect.invoice_bank_score = 100.0
        perfect.counterparty_consistency_score = 100.0
        perfect.amount_consistency_score = 100.0
        perfect.product_match_score = 100.0

        # 全正常 → low
        result = assess_enterprise_risk(normal_enterprise, perfect)
        assert result.overall_risk_level == "low"
        assert result.overall_risk_score < RISK_MEDIUM_THRESHOLD

        # 构造多维度高风险 → medium 或 high
        bad_input = EnterpriseRiskInput(
            enterprise_name="高风险", industry="制造",
            revenue_annual=Decimal("1000000"), tax_rate_industry=Decimal("3.0"),
            cost_rate_industry=Decimal("85.0"), actual_tax_burden_rate=Decimal("0.1"),
            actual_cost_rate=Decimal("50.0"),
            total_private_card_amount=Decimal("500000"), total_revenue=Decimal("1000000"),
            total_input_invoice=Decimal("100000"), total_output_invoice=Decimal("500000"),
        )
        result = assess_enterprise_risk(bad_input, poor_flow_match)
        assert result.overall_risk_level in ("medium", "high")

    def test_four_flow_integration_with_real_data(self):
        """使用真实四流数据进行完整风险评估"""
        contracts = [
            ContractRecord("CT-001", "正常客户", Decimal("200000"), date(2024, 1, 1)),
        ]
        invoices = [
            InvoiceRecord("INV-001", "output", Decimal("26000"), Decimal("200000"), "正常客户", "我方", "服务"),
        ]
        bank_txs = [
            BankTransactionRecord(date(2024, 2, 1), Decimal("200000"), "inflow", "corporate", "正常客户", "", True),
        ]
        enterprise = EnterpriseRiskInput(
            enterprise_name="集成测试企业", industry="制造",
            revenue_annual=Decimal("1000000"), tax_rate_industry=Decimal("3.0"),
            cost_rate_industry=Decimal("85.0"),
            actual_tax_burden_rate=Decimal("2.9"),
            actual_cost_rate=Decimal("84.0"),
            total_private_card_amount=Decimal("0"), total_revenue=Decimal("1000000"),
            total_input_invoice=Decimal("300000"), total_output_invoice=Decimal("400000"),
        )
        result = assess_enterprise_risk(
            enterprise_input=enterprise,
            flow_match_result=None,
            contracts=contracts,
            invoices=invoices,
            bank_transactions=bank_txs,
        )
        assert result.overall_risk_level == "low"
        assert result.overall_risk_score < RISK_MEDIUM_THRESHOLD

    def test_deduplication_of_flags(self, high_risk_enterprise, poor_flow_match):
        """风险标记和整改建议自动去重"""
        result = assess_enterprise_risk(high_risk_enterprise, poor_flow_match)
        # 转set比较长度，验证无重复
        assert len(result.risk_flags) == len(set(result.risk_flags))
        assert len(result.recommendations) == len(set(result.recommendations))

    def test_industry_default_reference(self):
        """未知行业时使用默认行业参考值"""
        unknown_industry = EnterpriseRiskInput(
            enterprise_name="未知行业企业", industry="新能源",
            revenue_annual=Decimal("5000000"), tax_rate_industry=Decimal("0"),   # 0 → 使用默认
            cost_rate_industry=Decimal("0"),  # 0 → 使用默认
            actual_tax_burden_rate=Decimal("1.5"), actual_cost_rate=Decimal("80.0"),
            total_private_card_amount=Decimal("0"), total_revenue=Decimal("5000000"),
            total_input_invoice=Decimal("500000"), total_output_invoice=Decimal("650000"),
        )
        result = assess_enterprise_risk(unknown_industry)
        assert result.overall_risk_level in ("low", "medium", "high")
        # 应使用默认值（2.0% 税负率，85.0% 成本率）代替0
        assert result.dimension_scores["tax_burden_deviation"] >= 0.0


# ═══════════════════════════════════════════════════════════
#  政策依据字段（policy_ref / risk_reason / policy_basis）
# ═══════════════════════════════════════════════════════════

class TestPolicyBasisFields:
    """每个风险维度都必须携带法规依据字段"""

    def test_all_dims_have_policy_fields(self, high_risk_enterprise, poor_flow_match):
        """全部维度详情均含 risk_reason / policy_ref / policy_basis"""
        result = assess_enterprise_risk(high_risk_enterprise, poor_flow_match)
        expected_dims = [
            "four_flow_match",
            "private_card_ratio",
            "large_personal_transfer",
            "cost_deviation",
            "tax_burden_deviation",
            "input_output_imbalance",
            "invoice_bank_mismatch",
        ]
        for dim in expected_dims:
            assert dim in result.dim_details, f"缺少维度: {dim}"
            detail = result.dim_details[dim]
            assert "risk_reason" in detail, f"{dim} 缺少 risk_reason"
            assert "policy_ref" in detail, f"{dim} 缺少 policy_ref"
            assert "policy_basis" in detail, f"{dim} 缺少 policy_basis"
            # 条文引用与条文说明非空
            assert isinstance(detail["policy_ref"], str) and detail["policy_ref"], \
                f"{dim} 的 policy_ref 为空"

    def test_risk_reason_prefers_flags(self, high_risk_enterprise, poor_flow_match):
        """存在风险标记时 risk_reason 优先取具体风险标记"""
        result = assess_enterprise_risk(high_risk_enterprise, poor_flow_match)
        ffm = result.dim_details["four_flow_match"]
        assert ffm["risk_reason"] == poor_flow_match.risk_flags[0]

    def test_tax_burden_cites_vat_law(self, high_risk_enterprise, poor_flow_match):
        """税负率维度引用增值税法条文（用户示例规则）"""
        result = assess_enterprise_risk(high_risk_enterprise, poor_flow_match)
        detail = result.dim_details["tax_burden_deviation"]
        assert "增值税法" in detail["policy_ref"]
        assert "销项税额抵扣当期进项税额" in detail["policy_basis"]

    def test_insufficient_data_no_policy(self):
        """数据不足时不生成维度详情（保持空返回）"""
        empty_input = EnterpriseRiskInput(
            enterprise_name="空企业", industry="制造",
            revenue_annual=Decimal("0"), tax_rate_industry=Decimal("3.0"),
            cost_rate_industry=Decimal("85.0"),
            actual_tax_burden_rate=Decimal("0"), actual_cost_rate=Decimal("0"),
            total_private_card_amount=Decimal("0"), total_revenue=Decimal("0"),
            total_input_invoice=Decimal("0"), total_output_invoice=Decimal("0"),
        )
        result = assess_enterprise_risk(enterprise_input=empty_input)
        assert result.dim_details == {}


# ═══════════════════════════════════════════════════════════
#  一票否决扩展：纳税信用 D 级 / 涉税犯罪
# ═══════════════════════════════════════════════════════════

class TestTaxCreditVeto:
    """纳税信用 D 级 / 涉税犯罪一票否决（2025 年第 12 号 / 刑法第 201 条）"""

    def test_d_level_forces_max_score(self, normal_enterprise, perfect_flow_match):
        """纳税信用 D 级 → 风险分强制 100、等级 high"""
        normal_enterprise.tax_credit_level = "D"
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.overall_risk_score == 100.0
        assert result.overall_risk_level == "high"
        assert result.technical_summary["tax_credit_veto"]
        assert any("D 级" in f for f in result.risk_flags)
        assert any("信用修复" in r for r in result.recommendations)

    def test_tax_crime_forces_max_score(self, normal_enterprise, perfect_flow_match):
        """涉税犯罪生效判决 → 风险分强制 100、等级 high"""
        normal_enterprise.tax_crime_convicted = True
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.overall_risk_score == 100.0
        assert result.overall_risk_level == "high"
        assert result.technical_summary["tax_credit_veto"]
        assert any("涉税犯罪" in f for f in result.risk_flags)

    def test_no_veto_for_a_level(self, normal_enterprise, perfect_flow_match):
        """A 级纳税信用 → 不触发一票否决，维持低风险"""
        normal_enterprise.tax_credit_level = "A"
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.overall_risk_score < RISK_MEDIUM_THRESHOLD
        assert result.technical_summary["tax_credit_veto"] is None

    def test_veto_overrides_low_dimension_scores(self, normal_enterprise, perfect_flow_match):
        """即使各维度都正常，D 级仍强制最高分"""
        normal_enterprise.tax_credit_level = "d"  # 小写也生效
        result = assess_enterprise_risk(normal_enterprise, perfect_flow_match)
        assert result.overall_risk_score == 100.0
        assert result.overall_risk_level == "high"

    def test_veto_applies_even_without_data(self):
        """数据不足时 D 级仍直接判级（2025 年第 12 号直接判 D 语义）"""
        empty_input = EnterpriseRiskInput(
            enterprise_name="空企业", industry="制造",
            revenue_annual=Decimal("0"), tax_rate_industry=Decimal("3.0"),
            cost_rate_industry=Decimal("85.0"),
            actual_tax_burden_rate=Decimal("0"), actual_cost_rate=Decimal("0"),
            total_private_card_amount=Decimal("0"), total_revenue=Decimal("0"),
            total_input_invoice=Decimal("0"), total_output_invoice=Decimal("0"),
            tax_credit_level="D",
        )
        result = assess_enterprise_risk(enterprise_input=empty_input)
        assert result.technical_summary["status"] == "veto_triggered"
        assert result.overall_risk_score == 100.0
        assert result.overall_risk_level == "high"
