"""
税收优惠适用性校验单元测试

覆盖场景：
  - 小微企业条件逐一验证（从业人数、资产总额、应纳税所得额）
  - 四种状态判定（enjoying_correctly/incorrectly/should_enjoy_but_not/not_applicable）
  - 高新技术企业动态监测提示
  - 行业专项优惠匹配
  - 恰好等于阈值边界
  - 零值输入
"""

import pytest

from app.core.tax_preference import (
    check_tax_preference,
    PreferenceCheckInput,
    PreferenceCheckResult,
    SMALL_MICRO_THRESHOLDS,
    HIGH_TECH_MONITORING_NOTE,
    INDUSTRY_PREFERENCES,
)


class TestSmallMicroEligible:
    """小微企业条件核验"""

    def test_all_conditions_met(self):
        """全部条件满足"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50,
            total_assets=10_000_000.0,
            annual_profit=1_000_000.0,
            is_high_tech=False,
            is_small_micro=True,
            industry="制造",
        ))
        assert result.small_micro_eligible is True
        assert result.current_status == "enjoying_correctly"

    def test_employee_exceeded(self):
        """从业人数超标"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=350,
            total_assets=10_000_000.0,
            annual_profit=1_000_000.0,
            is_high_tech=False,
            is_small_micro=False,
            industry="制造",
        ))
        assert result.small_micro_eligible is False
        assert result.small_micro_conditions["employee_count"]["passed"] is False

    def test_assets_exceeded(self):
        """资产总额超标"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=100,
            total_assets=60_000_000.0,
            annual_profit=1_000_000.0,
            is_high_tech=False,
            is_small_micro=False,
            industry="制造",
        ))
        assert result.small_micro_eligible is False
        assert result.small_micro_conditions["total_assets"]["passed"] is False

    def test_profit_exceeded(self):
        """应纳税所得额超标"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=100,
            total_assets=10_000_000.0,
            annual_profit=5_000_000.0,
            is_high_tech=False,
            is_small_micro=False,
            industry="制造",
        ))
        assert result.small_micro_eligible is False
        assert result.small_micro_conditions["annual_profit"]["passed"] is False

    def test_exact_threshold_values(self):
        """恰好等于阈值——视为满足"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=SMALL_MICRO_THRESHOLDS["max_employees"],
            total_assets=SMALL_MICRO_THRESHOLDS["max_assets"],
            annual_profit=SMALL_MICRO_THRESHOLDS["max_annual_profit"],
            is_high_tech=False,
            is_small_micro=True,
            industry="制造",
        ))
        assert result.small_micro_eligible is True
        assert result.small_micro_conditions["employee_count"]["passed"] is True
        assert result.small_micro_conditions["total_assets"]["passed"] is True
        assert result.small_micro_conditions["annual_profit"]["passed"] is True


class TestStatusDetermination:
    """状态判定逻辑"""

    def test_enjoying_correctly(self):
        """合格且正在享受 → enjoying_correctly"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=False, is_small_micro=True, industry="制造",
        ))
        assert result.current_status == "enjoying_correctly"

    def test_should_enjoy_but_not(self):
        """合格但未享受 → should_enjoy_but_not"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=False, is_small_micro=False, industry="制造",
        ))
        assert result.current_status == "should_enjoy_but_not"
        assert any("符合小微企业条件" in r for r in result.recommendations)

    def test_enjoying_incorrectly(self):
        """不合格但仍在享受 → enjoying_incorrectly"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=500, total_assets=100_000_000.0, annual_profit=10_000_000.0,
            is_high_tech=False, is_small_micro=True, industry="制造",
        ))
        assert result.current_status == "enjoying_incorrectly"
        assert any("不满足条件" in r for r in result.recommendations)

    def test_not_applicable(self):
        """不合格也未享受 → not_applicable"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=500, total_assets=100_000_000.0, annual_profit=10_000_000.0,
            is_high_tech=False, is_small_micro=False, industry="制造",
        ))
        assert result.current_status == "not_applicable"


class TestHighTech:
    """高新技术企业监测"""

    def test_high_tech_monitoring(self):
        """高企应触发动态监测提示"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=True, is_small_micro=True, industry="制造",
        ))
        assert result.high_tech_risk is not None
        assert "动态摘帽" in result.high_tech_risk
        assert HIGH_TECH_MONITORING_NOTE in result.high_tech_risk
        assert any("高新" in r for r in result.recommendations)

    def test_non_high_tech_no_monitoring(self):
        """非高企无监测提示"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=False, is_small_micro=True, industry="制造",
        ))
        assert result.high_tech_risk is None


class TestIndustryPreferences:
    """行业专项优惠"""

    def test_known_industry(self):
        """已知行业返回专项优惠"""
        for industry, prefs in INDUSTRY_PREFERENCES.items():
            result = check_tax_preference(PreferenceCheckInput(
                employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
                is_high_tech=False, is_small_micro=False, industry=industry,
            ))
            assert result.industry_preferences == prefs

    def test_unknown_industry(self):
        """未知行业返回空列表"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=False, is_small_micro=False, industry="新能源",
        ))
        assert result.industry_preferences == []


class TestEdgeCases:
    """边界场景"""

    def test_zero_all_values(self):
        """全部零值输入"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=0, total_assets=0.0, annual_profit=0.0,
            is_high_tech=False, is_small_micro=False, industry="制造",
        ))
        assert result.small_micro_eligible is True  # 零值满足 ≤ 阈值
        assert result.current_status == "should_enjoy_but_not"

    def test_negative_profit(self):
        """负利润——仍满足条件（≤阈值）"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=-100_000.0,
            is_high_tech=False, is_small_micro=False, industry="制造",
        ))
        assert result.small_micro_eligible is True


class TestReturnStructure:
    """返回值结构验证"""

    def test_result_type(self):
        """返回值类型正确"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=False, is_small_micro=True, industry="制造",
        ))
        assert isinstance(result, PreferenceCheckResult)
        assert isinstance(result.small_micro_eligible, bool)
        assert isinstance(result.small_micro_conditions, dict)
        assert len(result.small_micro_conditions) == 3
        assert isinstance(result.current_status, str)
        assert isinstance(result.recommendations, list)
        assert isinstance(result.business_narrative, str)
        assert isinstance(result.technical_summary, dict)

    def test_conditions_three_keys(self):
        """三个条件全部包含"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=False, is_small_micro=True, industry="制造",
        ))
        for key in ["employee_count", "total_assets", "annual_profit"]:
            c = result.small_micro_conditions[key]
            assert "value" in c
            assert "threshold" in c
            assert "passed" in c

    def test_technical_summary(self):
        """技术摘要完整"""
        result = check_tax_preference(PreferenceCheckInput(
            employee_count=50, total_assets=5_000_000.0, annual_profit=500_000.0,
            is_high_tech=True, is_small_micro=True, industry="制造",
        ))
        ts = result.technical_summary
        assert ts["small_micro_eligible"] is True
        assert ts["high_tech_monitoring"] is True
        assert ts["industry"] == "制造"
        assert "conditions" in ts
