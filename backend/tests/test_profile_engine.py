"""
心理画像评分模型单元测试

覆盖场景：
  - 正常场景：全维度正常、低偏差企业主
  - 边界场景：单维度高偏差、多维度中偏差、小微企业/高新企业调整
  - 异常场景：全维度极端偏差、缺失默认数据
  - 结构验证：返回值完整性、分数范围、商业语言输出
"""

import pytest

from app.core.profile_engine import (
    calculate_psychological_profile,
    BehavioralData,
    ProfileResult,
    BIAS_CN,
    INTERVENTION_STRATEGIES,
)


# ═══════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def normal_behavior():
    """正常合规的企业行为数据"""
    return BehavioralData(
        private_card_ratio=0.0,
        tax_burden_deviation=0.0,
        historical_risk_count=0,
        risk_recurrence_rate=0.0,
        four_flow_match_score=98.0,
        undeclared_revenue_ratio=0.0,
        remediation_completion_rate=98.0,
        consecutive_high_risk_periods=0,
        is_high_tech=False,
        is_small_micro=True,
        revenue_annual=500.0,
    )


@pytest.fixture
def extreme_behavior():
    """极端偏差——全维度异常"""
    return BehavioralData(
        private_card_ratio=0.95,
        tax_burden_deviation=5.0,
        historical_risk_count=10,
        risk_recurrence_rate=0.9,
        four_flow_match_score=10.0,
        undeclared_revenue_ratio=0.8,
        remediation_completion_rate=5.0,
        consecutive_high_risk_periods=8,
        is_high_tech=False,
        is_small_micro=True,
        revenue_annual=200.0,
    )


# ═══════════════════════════════════════════════════════════
#  正常场景
# ═══════════════════════════════════════════════════════════

class TestNormalScenarios:
    """正常企业主——低心理偏差"""

    def test_all_normal_low_scores(self, normal_behavior):
        """全部正常数据 → 各维度接近0分"""
        result = calculate_psychological_profile(normal_behavior)
        assert result.control_desire_score == 0
        assert result.loss_aversion_score == 0
        assert result.optimism_bias_score == 0
        assert result.control_illusion_score <= 10
        assert result.short_termism_score == 0
        assert result.defensiveness_score <= 3
        assert result.deviation_index < 10.0
        # 正常数据最多有2个非零低分被标记（防御心理+控制错觉各2分）
        assert len(result.dominant_biases) <= 2

    def test_return_type(self, normal_behavior):
        """返回值类型正确"""
        result = calculate_psychological_profile(normal_behavior)
        assert isinstance(result, ProfileResult)
        assert isinstance(result.control_desire_score, int)
        assert isinstance(result.loss_aversion_score, int)
        assert isinstance(result.optimism_bias_score, int)
        assert isinstance(result.control_illusion_score, int)
        assert isinstance(result.short_termism_score, int)
        assert isinstance(result.defensiveness_score, int)
        assert isinstance(result.deviation_index, float)
        assert isinstance(result.dominant_biases, list)
        assert isinstance(result.intervention_strategy, dict)
        assert isinstance(result.business_narrative, str)
        assert isinstance(result.technical_summary, dict)

    def test_business_narrative_structure(self, normal_behavior):
        """商业语言叙述结构正确"""
        result = calculate_psychological_profile(normal_behavior)
        assert "心理画像" in result.business_narrative
        assert "综合偏差指数" in result.business_narrative
        assert "掌控欲" in result.business_narrative
        assert "损失厌恶" in result.business_narrative

    def test_technical_summary_structure(self, normal_behavior):
        """技术摘要结构完整"""
        result = calculate_psychological_profile(normal_behavior)
        ts = result.technical_summary
        assert "scores" in ts
        assert "deviation_index" in ts
        assert "dominant_biases" in ts
        assert "intervention_strategies" in ts
        assert "metadata" in ts
        assert ts["metadata"]["model_version"] == "1.0.0"
        assert "bias_count" in ts["metadata"]

    def test_intervention_strategies_all_bias_types(self, normal_behavior):
        """干预策略覆盖所有六种偏差类型"""
        result = calculate_psychological_profile(normal_behavior)
        for bias in BIAS_CN:
            assert bias in result.intervention_strategy
            # 即使是 low 也应该有策略
            assert len(result.intervention_strategy[bias]) > 0


# ═══════════════════════════════════════════════════════════
#  各维度独立测试
# ═══════════════════════════════════════════════════════════

class TestControlDesire:
    """掌控欲维度测试"""

    def test_no_private_card(self):
        """无私卡 → 0分"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.control_desire_score == 0

    def test_high_private_card(self):
        """高私卡占比"""
        data = BehavioralData(
            private_card_ratio=0.6, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
            is_small_micro=True,
        )
        result = calculate_psychological_profile(data)
        # 0.6*100=60 + small_micro bonus 15 = 75
        assert result.control_desire_score >= 60

    def test_private_card_100pct(self):
        """私卡占比100%"""
        data = BehavioralData(
            private_card_ratio=1.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
            is_small_micro=True,
        )
        result = calculate_psychological_profile(data)
        assert result.control_desire_score == 100  # capped at 100

    def test_high_tech_discount(self):
        """高新技术企业减成"""
        # 高私卡但高新企业
        data = BehavioralData(
            private_card_ratio=0.5, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
            is_high_tech=True, is_small_micro=False,
        )
        result = calculate_psychological_profile(data)
        # 0.5*100=50 - 20(high_tech) = 30
        assert result.control_desire_score == 30

    def test_high_tech_and_small_micro_combined(self):
        """高新技术+小微企业组合"""
        data = BehavioralData(
            private_card_ratio=0.4, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
            is_high_tech=True, is_small_micro=True,
        )
        result = calculate_psychological_profile(data)
        # 0.4*100=40 + 15(small_micro) - 20(high_tech) = 35
        assert result.control_desire_score == 35


class TestLossAversion:
    """损失厌恶维度测试"""

    def test_no_deviation(self):
        """零偏离 → 0分"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.loss_aversion_score == 0

    def test_negative_deviation_returns_zero(self):
        """负偏离（高于行业平均值）→ 0分"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=-1.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.loss_aversion_score == 0

    def test_moderate_deviation(self):
        """中等偏离 1.5%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=1.5,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        # ≤1.5 → 20 + (1.5-0.5)*40 = 20 + 40 = 60
        assert result.loss_aversion_score == 60

    def test_high_deviation(self):
        """高偏离 4.0%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=4.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        # >3.0 → 90 + (4.0-3.0)*3 = 90 + 3 = 93
        assert result.loss_aversion_score == 93

    def test_extreme_deviation(self):
        """极端偏离 10%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=10.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.loss_aversion_score == 100  # capped


class TestOptimismBias:
    """乐观偏差维度测试"""

    def test_no_history(self):
        """无历史风险 → 0分"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.optimism_bias_score == 0

    def test_moderate_history(self):
        """中等历史风险"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=4, risk_recurrence_rate=0.5,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=3,
        )
        result = calculate_psychological_profile(data)
        # historical_risk_count=4 → 25 (>=3)
        # consecutive=3 → 20 (>=2)
        # recurrence 0.5 → 15 (>0.4)
        # total = 60
        assert result.optimism_bias_score == 60

    def test_high_everything(self):
        """全部高风险指标"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=6, risk_recurrence_rate=0.85,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=5,
        )
        result = calculate_psychological_profile(data)
        # >=5 risks=40, >=4 periods=40, >0.7 recurrence=25
        # total = 105 → capped at 100
        assert result.optimism_bias_score == 100


class TestControlIllusion:
    """控制错觉维度测试"""

    def test_perfect_match(self):
        """四流匹配完美 → 低控制错觉"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.control_illusion_score == 0

    def test_poor_match(self):
        """四流匹配差 → 高控制错觉"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=25.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.control_illusion_score == 75  # 100 - 25

    def test_terrible_match(self):
        """四流匹配极差"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=0.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.control_illusion_score == 100


class TestShortTermism:
    """短期主义维度测试"""

    def test_no_undeclared(self):
        """无未申报收入 → 0分"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.short_termism_score == 0

    def test_low_undeclared(self):
        """低未申报 5%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.05,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert 10 <= result.short_termism_score <= 20  # 0.05 * 300 = 15

    def test_moderate_undeclared(self):
        """中等未申报 25%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.25,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        # 0.1-0.3 range: 30 + (0.25-0.1)*200 = 30 + 30 = 60
        assert result.short_termism_score == 60

    def test_high_undeclared(self):
        """高未申报 60%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.6,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        # >0.5: 90 + (0.6-0.5)*50 = 90 + 5 = 95
        assert result.short_termism_score == 95


class TestDefensiveness:
    """防御心理维度测试"""

    def test_full_completion(self):
        """整改完成率100% → 0分"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.defensiveness_score == 0

    def test_over_100_completion(self):
        """整改完成率超过100%（边界）→ 0分"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=150.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.defensiveness_score == 0

    def test_half_completion(self):
        """整改完成率50%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=50.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.defensiveness_score == 50

    def test_zero_completion(self):
        """整改完成率0%"""
        data = BehavioralData(
            private_card_ratio=0.0, tax_burden_deviation=0.0,
            historical_risk_count=0, risk_recurrence_rate=0.0,
            four_flow_match_score=100.0, undeclared_revenue_ratio=0.0,
            remediation_completion_rate=0.0, consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        assert result.defensiveness_score == 100


# ═══════════════════════════════════════════════════════════
#  综合场景
# ═══════════════════════════════════════════════════════════

class TestComprehensiveScenarios:
    """综合场景测试"""

    def test_extreme_all_dimensions(self, extreme_behavior):
        """极端偏差——所有维度接近100"""
        result = calculate_psychological_profile(extreme_behavior)
        assert result.control_desire_score >= 80
        assert result.loss_aversion_score >= 80
        assert result.optimism_bias_score >= 80
        assert result.control_illusion_score >= 80
        assert result.short_termism_score >= 80
        assert result.defensiveness_score >= 80
        assert result.deviation_index >= 60.0
        # 应有主导偏差（现在取top 2）
        assert len(result.dominant_biases) == 2

    def test_dominant_biases_threshold(self, extreme_behavior):
        """主导偏差阈值为60分"""
        result = calculate_psychological_profile(extreme_behavior)
        for bias in result.dominant_biases:
            score = getattr(result, f"{bias}_score")
            assert score >= 60, f"{bias} score={score} 被标记为主导偏差但低于60"

    def test_deviation_index_average(self, extreme_behavior):
        """综合偏差指数为六维平均值"""
        result = calculate_psychological_profile(extreme_behavior)
        expected_avg = (
            result.control_desire_score
            + result.loss_aversion_score
            + result.optimism_bias_score
            + result.control_illusion_score
            + result.short_termism_score
            + result.defensiveness_score
        ) / 6
        # deviation_index 经过 round(..., 2) 处理，使用较大容差
        assert result.deviation_index == pytest.approx(expected_avg, rel=0.01)

    def test_intervention_high_level_triggers(self, extreme_behavior):
        """高风险偏差触发对应级别干预策略"""
        result = calculate_psychological_profile(extreme_behavior)
        for bias in result.dominant_biases:
            strategy = result.intervention_strategy[bias]
            assert len(strategy) > 0
            # high等效应触发更长的策略文字
            assert len(strategy) > 10  # 至少不是空串或简单几个字

    def test_score_range_all_dimensions(self, extreme_behavior, normal_behavior):
        """所有维度得分在0-100范围内"""
        for data in [normal_behavior, extreme_behavior]:
            result = calculate_psychological_profile(data)
            assert 0 <= result.control_desire_score <= 100
            assert 0 <= result.loss_aversion_score <= 100
            assert 0 <= result.optimism_bias_score <= 100
            assert 0 <= result.control_illusion_score <= 100
            assert 0 <= result.short_termism_score <= 100
            assert 0 <= result.defensiveness_score <= 100
            assert 0.0 <= result.deviation_index <= 100.0

    def test_dominant_biases_sorted_desc(self, extreme_behavior):
        """主导偏差按分数降序排列"""
        result = calculate_psychological_profile(extreme_behavior)
        if len(result.dominant_biases) >= 2:
            prev_score = float("inf")
            for bias in result.dominant_biases:
                score = getattr(result, f"{bias}_score")
                assert score <= prev_score, f"主导偏差未按降序排列: {result.dominant_biases}"
                prev_score = score

    def test_default_values_conservative(self):
        """默认值（全为默认）→ 保守评分，不崩溃"""
        data = BehavioralData(
            private_card_ratio=0.0,
            tax_burden_deviation=0.0,
            historical_risk_count=0,
            risk_recurrence_rate=0.0,
            four_flow_match_score=100.0,
            undeclared_revenue_ratio=0.0,
            remediation_completion_rate=100.0,
            consecutive_high_risk_periods=0,
        )
        result = calculate_psychological_profile(data)
        # 默认值应为低风险
        assert result.deviation_index < 20.0
        assert len(result.dominant_biases) == 0
        assert result.business_narrative  # 必须有商业语言输出
        assert result.technical_summary

    def test_mixed_scenario_moderate(self):
        """中等偏差的混合场景"""
        data = BehavioralData(
            private_card_ratio=0.2,
            tax_burden_deviation=1.0,
            historical_risk_count=2,
            risk_recurrence_rate=0.3,
            four_flow_match_score=65.0,
            undeclared_revenue_ratio=0.15,
            remediation_completion_rate=55.0,
            consecutive_high_risk_periods=1,
        )
        result = calculate_psychological_profile(data)
        # 各维度应在中低范围，偏差指数用新公式
        assert 0 <= result.deviation_index <= 100.0
        assert result.business_narrative  # 必须有叙述

    def test_biases_count_metadata(self, extreme_behavior, normal_behavior):
        """元数据中 bias_count 正确"""
        result_normal = calculate_psychological_profile(normal_behavior)
        result_extreme = calculate_psychological_profile(extreme_behavior)
        assert result_normal.technical_summary["metadata"]["bias_count"] <= 2
        assert result_extreme.technical_summary["metadata"]["bias_count"] >= 2

    def test_highest_bias_metadata(self, extreme_behavior):
        """元数据中 highest_bias 正确记录（中文名称）"""
        result = calculate_psychological_profile(extreme_behavior)
        ts = result.technical_summary
        if result.dominant_biases:
            # metadata stores Chinese name from BIAS_CN
            expected_cn = BIAS_CN.get(result.dominant_biases[0], result.dominant_biases[0])
            assert ts["metadata"]["highest_bias"] == expected_cn
