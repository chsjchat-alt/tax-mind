"""
心理干预策略引擎单元测试

覆盖场景：
  - 五层干预策略全部生成
  - 优先级默认顺序
  - 优先级根据主导偏差调整
  - 各偏差类型对应优先级验证
  - 商业语言叙述生成
  - 边界场景（空偏差、极值）
"""

import pytest

from app.core.intervention import (
    generate_intervention,
    InterventionInput,
    InterventionResult,
    InterventionLayer,
    INTERVENTION_TEMPLATES,
)


class TestBasicGeneration:
    """基本干预生成"""

    def test_all_five_layers_generated(self):
        """生成全部五层干预"""
        result = generate_intervention(InterventionInput(
            risk_level="medium",
            deviation_index=50.0,
            dominant_biases=[],
            audit_probability=0.25,
            expected_loss=500000.0,
            remediation_cost=100000.0,
        ))
        assert len(result.layers) == 5
        for i, layer in enumerate(result.layers, 1):
            assert layer.layer == i
            assert isinstance(layer, InterventionLayer)
            assert len(layer.content) > 0
            assert len(layer.theory) > 0

    def test_layer_names(self):
        """每层名称正确"""
        result = generate_intervention(InterventionInput(
            risk_level="low",
            deviation_index=10.0,
            dominant_biases=[],
            audit_probability=0.05,
            expected_loss=10000.0,
            remediation_cost=5000.0,
        ))
        expected_names = ["打破乐观偏差", "削弱控制错觉", "重构损失认知", "缓解认知失调", "锚定长期预期"]
        for i, layer in enumerate(result.layers):
            assert layer.name == expected_names[i]

    def test_visual_type_per_layer(self):
        """每层有可视化类型"""
        result = generate_intervention(InterventionInput(
            risk_level="low",
            deviation_index=10.0,
            dominant_biases=[],
            audit_probability=0.05,
            expected_loss=10000.0,
            remediation_cost=5000.0,
        ))
        visual_types = [layer.visual_type for layer in result.layers]
        assert visual_types[0] == "card"
        assert visual_types[1] == "animation"
        assert visual_types[3] == "text"


class TestPriorityAdjustment:
    """优先级调整逻辑"""

    def test_no_biases_default_order(self):
        """无主导偏差 → 默认顺序1-5"""
        result = generate_intervention(InterventionInput(
            risk_level="low",
            deviation_index=10.0,
            dominant_biases=[],
            audit_probability=0.05,
            expected_loss=10000.0,
            remediation_cost=5000.0,
        ))
        assert result.priority_order == [1, 2, 3, 4, 5]

    def test_optimism_bias_priority_first(self):
        """乐观偏差 → 第一层优先"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=80.0,
            dominant_biases=["optimism_bias"],
            audit_probability=0.50,
            expected_loss=1000000.0,
            remediation_cost=200000.0,
        ))
        assert result.priority_order[0] == 1  # 第一层（打破乐观偏差）应排第一

    def test_control_illusion_priority_second(self):
        """控制错觉 → 第二层优先"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=70.0,
            dominant_biases=["control_illusion"],
            audit_probability=0.50,
            expected_loss=500000.0,
            remediation_cost=100000.0,
        ))
        assert result.priority_order[0] == 2

    def test_loss_aversion_priority_third(self):
        """损失厌恶 → 第三层优先"""
        result = generate_intervention(InterventionInput(
            risk_level="medium",
            deviation_index=60.0,
            dominant_biases=["loss_aversion"],
            audit_probability=0.25,
            expected_loss=300000.0,
            remediation_cost=50000.0,
        ))
        assert result.priority_order[0] == 3

    def test_defensiveness_priority_fourth(self):
        """防御心理 → 第四层优先"""
        result = generate_intervention(InterventionInput(
            risk_level="medium",
            deviation_index=50.0,
            dominant_biases=["defensiveness"],
            audit_probability=0.25,
            expected_loss=200000.0,
            remediation_cost=80000.0,
        ))
        assert result.priority_order[0] == 4

    def test_short_termism_priority_fifth(self):
        """短期主义 → 第五层优先"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=75.0,
            dominant_biases=["short_termism"],
            audit_probability=0.50,
            expected_loss=800000.0,
            remediation_cost=150000.0,
        ))
        assert result.priority_order[0] == 5

    def test_multiple_biases_priority(self):
        """多个主导偏差 → 多个层级提前"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=85.0,
            dominant_biases=["optimism_bias", "loss_aversion", "short_termism"],
            audit_probability=0.80,
            expected_loss=2000000.0,
            remediation_cost=300000.0,
        ))
        # 前三个应该是 1, 3, 5（按偏差出现顺序）
        assert result.priority_order[:3] == [1, 3, 5]
        assert len(result.priority_order) == 5
        assert set(result.priority_order) == {1, 2, 3, 4, 5}

    def test_control_desire_maps_to_layer_2(self):
        """掌控欲映射到第二层"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=70.0,
            dominant_biases=["control_desire"],
            audit_probability=0.30,
            expected_loss=500000.0,
            remediation_cost=100000.0,
        ))
        assert result.priority_order[0] == 2


class TestContentFormatting:
    """干预内容格式化"""

    def test_content_includes_audit_probability(self):
        """内容中包含稽查概率"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=80.0,
            dominant_biases=["optimism_bias"],
            audit_probability=0.80,
            expected_loss=1000000.0,
            remediation_cost=200000.0,
        ))
        # 第一层内容应包含稽查概率
        layer1 = result.layers[0]  # 打破乐观偏差
        assert "80%" in layer1.content

    def test_content_includes_expected_loss(self):
        """内容中包含期望损失"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=80.0,
            dominant_biases=["loss_aversion"],
            audit_probability=0.50,
            expected_loss=999999.0,
            remediation_cost=100000.0,
        ))
        layer3 = result.layers[2]  # 重构损失认知
        assert "999,999" in layer3.content or "1,000,000" in layer3.content

    def test_content_includes_remediation_cost(self):
        """内容中包含整改成本"""
        result = generate_intervention(InterventionInput(
            risk_level="medium",
            deviation_index=50.0,
            dominant_biases=[],
            audit_probability=0.25,
            expected_loss=500000.0,
            remediation_cost=99999.0,
        ))
        layer3 = result.layers[2]
        assert "99,999" in layer3.content or "100,000" in layer3.content


class TestEdgeCases:
    """边界场景"""

    def test_zero_deviation_index(self):
        """偏差指数为0"""
        result = generate_intervention(InterventionInput(
            risk_level="low",
            deviation_index=0.0,
            dominant_biases=[],
            audit_probability=0.0,
            expected_loss=0.0,
            remediation_cost=0.0,
        ))
        assert len(result.layers) == 5
        assert len(result.business_narrative) > 0

    def test_max_deviation_index(self):
        """偏差指数为100"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=100.0,
            dominant_biases=["optimism_bias", "control_illusion", "loss_aversion",
                             "defensiveness", "short_termism"],
            audit_probability=1.0,
            expected_loss=10_000_000.0,
            remediation_cost=1_000_000.0,
        ))
        assert len(result.layers) == 5
        assert len(result.priority_order) == 5

    def test_empty_biases_but_all_levels(self):
        """空偏差列表但所有级别正常"""
        result = generate_intervention(InterventionInput(
            risk_level="low",
            deviation_index=0.0,
            dominant_biases=[],
            audit_probability=0.01,
            expected_loss=0.0,
            remediation_cost=0.0,
        ))
        assert result.business_narrative
        assert result.technical_summary


class TestRiskScoreCalculation:
    """风险评分计算"""

    def test_low_risk_score(self):
        """低风险评分"""
        result = generate_intervention(InterventionInput(
            risk_level="low",
            deviation_index=30.0,
            dominant_biases=[],
            audit_probability=0.05,
            expected_loss=10000.0,
            remediation_cost=5000.0,
        ))
        # low multiplier=0.3 → 30*0.3=9.0
        assert result.technical_summary["risk_score"] == pytest.approx(9.0)

    def test_medium_risk_score(self):
        """中风险评分"""
        result = generate_intervention(InterventionInput(
            risk_level="medium",
            deviation_index=50.0,
            dominant_biases=[],
            audit_probability=0.25,
            expected_loss=50000.0,
            remediation_cost=20000.0,
        ))
        # medium multiplier=1.0 → 50
        assert result.technical_summary["risk_score"] == pytest.approx(50.0)

    def test_high_risk_score(self):
        """高风险评分"""
        result = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=60.0,
            dominant_biases=[],
            audit_probability=0.50,
            expected_loss=500000.0,
            remediation_cost=100000.0,
        ))
        # high multiplier=2.0 → 120, capped at 100
        assert result.technical_summary["risk_score"] == 100.0


class TestReturnStructure:
    """返回值结构验证"""

    def test_result_type(self):
        """返回值类型正确"""
        result = generate_intervention(InterventionInput(
            risk_level="medium",
            deviation_index=50.0,
            dominant_biases=["optimism_bias"],
            audit_probability=0.30,
            expected_loss=500000.0,
            remediation_cost=100000.0,
        ))
        assert isinstance(result, InterventionResult)
        assert isinstance(result.layers, list)
        assert isinstance(result.priority_order, list)
        assert isinstance(result.business_narrative, str)
        assert isinstance(result.technical_summary, dict)

    def test_technical_summary_flags(self):
        """技术摘要标志正确"""
        # 无偏差 → adjusted=False
        result1 = generate_intervention(InterventionInput(
            risk_level="low",
            deviation_index=10.0,
            dominant_biases=[],
            audit_probability=0.05,
            expected_loss=10000.0,
            remediation_cost=5000.0,
        ))
        assert result1.technical_summary["adjusted"] is False

        # 有偏差且顺序不同 → adjusted=True
        result2 = generate_intervention(InterventionInput(
            risk_level="high",
            deviation_index=80.0,
            dominant_biases=["short_termism"],  # 第五层优先 → 顺序与默认不同
            audit_probability=0.80,
            expected_loss=1000000.0,
            remediation_cost=200000.0,
        ))
        assert result2.technical_summary["adjusted"] is True

    def test_all_intervention_templates_exist(self):
        """五层模板全部存在"""
        for i in range(1, 6):
            assert i in INTERVENTION_TEMPLATES
            assert "name" in INTERVENTION_TEMPLATES[i]
            assert "theory" in INTERVENTION_TEMPLATES[i]
            assert "content_template" in INTERVENTION_TEMPLATES[i]
            assert "visual_type" in INTERVENTION_TEMPLATES[i]
