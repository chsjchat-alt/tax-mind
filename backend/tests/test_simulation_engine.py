"""
沉浸式风险模拟器单元测试

覆盖场景：
  - 低/中/高风险三种模拟路径
  - 三个时间节点（6个月、1年、3年）数据正确性
  - 稽查概率矩阵验证
  - 损失框架话术生成
  - 案例引用加载
  - 边缘场景（零隐匿收入、零税率、零整改成本）
"""

import pytest

from app.core.simulation_engine import (
    run_simulation,
    SimulationInput,
    SimulationResult,
    TimePointResult,
    AUDIT_PROBABILITY_MATRIX,
    PENALTY_MULTIPLIER,
    LATE_FEE_DAILY_RATE,
)


class TestLowRiskSimulation:
    """低风险场景"""

    def test_low_risk_basic(self):
        """低风险：月隐匿5万，税率6%"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=50000.0,
            comprehensive_tax_rate=0.06,
            risk_level="low",
            remediation_cost=50000.0,
        ))
        assert len(result.time_points) == 3
        # 6个月节点的稽查概率应为5%
        assert result.time_points[0].audit_probability == pytest.approx(0.05)
        # 1年：10%
        assert result.time_points[1].audit_probability == pytest.approx(0.10)
        # 3年：20%
        assert result.time_points[2].audit_probability == pytest.approx(0.20)

        # 每月少缴税款=50000*0.06=3000，6个月=18000
        assert result.time_points[0].total_hidden_tax == 18000.0

    def test_low_risk_loss_frame(self):
        """低风险损失框架话术"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=30000.0,
            comprehensive_tax_rate=0.06,
            risk_level="low",
            remediation_cost=20000.0,
        ))
        assert "风险水平较低" in result.loss_frame_message
        assert len(result.loss_frame_message) > 0


class TestMediumRiskSimulation:
    """中风险场景"""

    def test_medium_risk_basic(self):
        """中风险：月隐匿10万"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=100000.0,
            comprehensive_tax_rate=0.06,
            risk_level="medium",
            remediation_cost=80000.0,
        ))
        # 6个月稽查概率=15%
        assert result.time_points[0].audit_probability == pytest.approx(0.15)
        # 1年=25%
        assert result.time_points[1].audit_probability == pytest.approx(0.25)
        # 3年=45%
        assert result.time_points[2].audit_probability == pytest.approx(0.45)

        # 中风险罚款倍数=1.5
        expected_penalty = round((100000 * 0.06 * 6) * 1.5 * 0.15, 2)
        assert result.time_points[0].expected_penalty == expected_penalty

    def test_medium_risk_loss_frame(self):
        """中风险损失框架话术"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=80000.0,
            comprehensive_tax_rate=0.06,
            risk_level="medium",
            remediation_cost=50000.0,
        ))
        assert "及早整改" in result.loss_frame_message


class TestHighRiskSimulation:
    """高风险场景"""

    def test_high_risk_basic(self):
        """高风险：月隐匿20万"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=200000.0,
            comprehensive_tax_rate=0.06,
            risk_level="high",
            remediation_cost=100000.0,
            monthly_reputation_loss=5000.0,
        ))
        # 3年稽查概率=80%
        assert result.time_points[2].audit_probability == pytest.approx(0.80)

        # 高风险罚款倍数=3.5
        assert result.time_points[0].expected_penalty > 0

    def test_high_risk_loss_frame(self):
        """高风险损失框架话术"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=150000.0,
            comprehensive_tax_rate=0.06,
            risk_level="high",
            remediation_cost=50000.0,
        ))
        assert "80%" in result.loss_frame_message or "80" in result.loss_frame_message

    def test_high_risk_recommendation_positive(self):
        """高风险时推荐立即整改"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=500000.0,
            comprehensive_tax_rate=0.06,
            risk_level="high",
            remediation_cost=100000.0,
        ))
        assert "建议立即" in result.recommendation or "强烈建议" in result.recommendation


class TestEdgeCases:
    """边界场景"""

    def test_zero_hidden_revenue(self):
        """隐匿收入为0"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=0.0,
            comprehensive_tax_rate=0.06,
            risk_level="high",
            remediation_cost=0.0,
        ))
        for tp in result.time_points:
            assert tp.total_hidden_tax == 0.0
            assert tp.expected_penalty == 0.0
            assert tp.expected_late_fee == 0.0
            assert tp.path_a_cost == 0.0

    def test_zero_tax_rate(self):
        """综合税率为0"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=100000.0,
            comprehensive_tax_rate=0.0,
            risk_level="medium",
            remediation_cost=50000.0,
        ))
        for tp in result.time_points:
            assert tp.total_hidden_tax == 0.0

    def test_zero_remediation_cost(self):
        """整改成本为0"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=100000.0,
            comprehensive_tax_rate=0.06,
            risk_level="medium",
            remediation_cost=0.0,
        ))
        for tp in result.time_points:
            assert tp.path_b_cost == 0.0
            # cost_difference 应为正值（A > B = 0）
            assert tp.cost_difference >= 0.0

    def test_high_remediation_cheaper_than_path_a(self):
        """整改成本远低于不合规期望成本"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=100000.0,
            comprehensive_tax_rate=0.13,
            risk_level="high",
            remediation_cost=10000.0,
        ))
        last = result.time_points[-1]
        # 3年节点：A应远大于B
        assert last.path_a_cost > last.path_b_cost, \
            f"path_a={last.path_a_cost}, path_b={last.path_b_cost}"


class TestReturnStructure:
    """返回值结构验证"""

    def test_result_type(self):
        """返回值类型正确"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=10000.0,
            comprehensive_tax_rate=0.06,
            risk_level="low",
            remediation_cost=5000.0,
        ))
        assert isinstance(result, SimulationResult)
        assert len(result.time_points) == 3
        assert isinstance(result.recommendation, str)
        assert isinstance(result.loss_frame_message, str)
        assert isinstance(result.case_references, list)
        assert isinstance(result.technical_summary, dict)

    def test_time_point_structure(self):
        """每个时间节点字段完整"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=10000.0,
            comprehensive_tax_rate=0.06,
            risk_level="low",
            remediation_cost=5000.0,
        ))
        for tp in result.time_points:
            assert isinstance(tp, TimePointResult)
            assert tp.period in ("6months", "1year", "3years")
            assert tp.months_elapsed in (6, 12, 36)
            assert tp.audit_probability > 0
            assert tp.path_a_cost >= 0
            assert tp.path_b_cost >= 0

    def test_technical_summary(self):
        """技术摘要完整"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=10000.0,
            comprehensive_tax_rate=0.06,
            risk_level="low",
            remediation_cost=5000.0,
        ))
        ts = result.technical_summary
        assert "input" in ts
        assert "penalty_multiplier" in ts
        assert "audit_probability_matrix_used" in ts
        assert "time_points" in ts
        assert "case_references_count" in ts

    def test_case_references_loaded(self):
        """案例引用正确加载"""
        result = run_simulation(SimulationInput(
            monthly_hidden_revenue=10000.0,
            comprehensive_tax_rate=0.06,
            risk_level="high",
            remediation_cost=5000.0,
            industry="批发零售",
        ))
        assert len(result.case_references) > 0
        # 应有XJ开头的案例ID
        assert any("XJ-" in ref for ref in result.case_references)


class TestAuditProbabilityMatrix:
    """稽查概率矩阵验证"""

    def test_probabilities_in_range(self):
        """所有稽查概率在0-1之间"""
        for level in ["low", "medium", "high"]:
            for period in ["6months", "1year", "3years"]:
                prob = AUDIT_PROBABILITY_MATRIX[level][period]
                assert 0 < prob <= 1.0, f"Invalid prob: {level}/{period}={prob}"

    def test_probabilities_increasing(self):
        """稽查概率随时间递增"""
        for level in ["low", "medium", "high"]:
            probs = AUDIT_PROBABILITY_MATRIX[level]
            assert probs["6months"] < probs["1year"] < probs["3years"], \
                f"{level}: probabilities not increasing"

    def test_probabilities_higher_for_high_risk(self):
        """高风险概率始终高于低风险"""
        for period in ["6months", "1year", "3years"]:
            assert AUDIT_PROBABILITY_MATRIX["high"][period] > AUDIT_PROBABILITY_MATRIX["low"][period]
