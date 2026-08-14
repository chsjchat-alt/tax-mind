"""
credit_veto（纳税信用D级 / 涉税犯罪一票否决）单元测试

依据：《纳税缴费信用管理办法》2025 年第 12 号 直接判D；
      《刑法》第 201 条 逃税罪。
"""
import pytest

from app.core.credit_veto import resolve_tax_credit_veto, D_CREDIT_LEVEL


class TestResolveTaxCreditVeto:
    def test_no_veto_when_not_rated(self):
        """未评级 / 空值 → 不触发"""
        assert resolve_tax_credit_veto() is None
        assert resolve_tax_credit_veto(tax_credit_level=None) is None
        assert resolve_tax_credit_veto(tax_credit_level="") is None
        assert resolve_tax_credit_veto(tax_credit_level="  ") is None

    def test_no_veto_for_a_b_c(self):
        """A/B/C 级 → 不触发"""
        for level in ("A", "B", "C", "a", "b", "c"):
            assert resolve_tax_credit_veto(tax_credit_level=level) is None

    def test_veto_for_d_level(self):
        """D 级 → 触发，返回否决原因"""
        reason = resolve_tax_credit_veto(tax_credit_level="D")
        assert reason is not None
        assert "D 级" in reason
        assert "2025" in reason

    def test_veto_case_insensitive(self):
        """小写 d 同样触发（入参规整化）"""
        assert resolve_tax_credit_veto(tax_credit_level="d") is not None

    def test_veto_for_tax_crime(self):
        """涉税犯罪生效判决 → 触发"""
        reason = resolve_tax_credit_veto(tax_crime_convicted=True)
        assert reason is not None
        assert "涉税犯罪" in reason
        assert "第 201 条" in reason

    def test_no_veto_when_no_crime(self):
        """未涉税犯罪且非 D 级 → 不触发"""
        assert resolve_tax_credit_veto(tax_crime_convicted=False) is None

    def test_crime_takes_priority_over_level(self):
        """涉税犯罪与 D 级同时存在 → 犯罪原因优先（更强法律后果）"""
        reason = resolve_tax_credit_veto(
            tax_credit_level="D", tax_crime_convicted=True,
        )
        assert "涉税犯罪" in reason

    def test_constant_d_credit_level(self):
        """导出常量 D_CREDIT_LEVEL 为 'D'"""
        assert D_CREDIT_LEVEL == "D"
