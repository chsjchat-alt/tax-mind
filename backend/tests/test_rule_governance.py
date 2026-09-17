"""
Rule ID 法规治理矩阵测试（对应 V4 §十一 + §九验收指标）

验收口径：
  - 失效/未复核规则必须挂起自动计算（route_to_manual）；
  - 相同输入参数下重算一致率 100%（calc_id 确定性）。
"""
from datetime import date

import pytest

from app.core.rule_governance import (
    ManualRoute,
    RuleExecutor,
    RuleNotExecutableError,
    RuleRegistry,
    RuleStatus,
)

# 审查基准日：终稿自审日（VAT-RATE-LEGACY-001 已于 2026-08-10 废止之后）
ON_DATE = date(2026, 9, 12)


@pytest.fixture(scope="module")
def registry() -> RuleRegistry:
    return RuleRegistry.load_default()


@pytest.fixture(scope="module")
def executor(registry: RuleRegistry) -> RuleExecutor:
    return RuleExecutor(registry=registry)


# ── 注册表：加载与状态 ──
class TestRegistry:
    def test_loads_all_fixture_rules(self, registry: RuleRegistry) -> None:
        assert len(registry.rules) >= 15

    def test_legacy_rule_repealed(self, registry: RuleRegistry) -> None:
        rule = registry.get("VAT-RATE-LEGACY-001")
        assert rule.status == RuleStatus.REPEALED

    def test_statutory_law_priority(self, registry: RuleRegistry) -> None:
        from app.core.rule_governance import RulePriority
        assert registry.get("VAT-EXEMPT-001").priority == RulePriority.STATUTORY_LAW
        assert registry.get("AGRI-DEEM-001").priority == RulePriority.NATIONAL_ADMIN_RULE

    def test_unknown_rule_raises(self, registry: RuleRegistry) -> None:
        with pytest.raises(Exception, match="未知规则"):
            registry.get("NOT-EXIST-001")


# ── 时效与复核闸门 ──
class TestGates:
    def test_active_rule_executable(self, registry: RuleRegistry) -> None:
        ok, reason = registry.get("AGRI-DEEM-001").is_executable(ON_DATE)
        assert ok and reason == "active"

    def test_repealed_rule_blocked(self, registry: RuleRegistry) -> None:
        """『去年能引用 ≠ 今天还能引用』：2011年38号必须被拦截"""
        ok, reason = registry.get("VAT-RATE-LEGACY-001").is_executable(ON_DATE)
        assert not ok and "status=repealed" in reason

    def test_superseded_rule_blocked(self, registry: RuleRegistry) -> None:
        """加计 1% 抵扣 2026-01-01 停止执行（V3.1 教训的实证之二）"""
        ok, reason = registry.get("VAT-INPUT-SUPP-001").is_executable(ON_DATE)
        assert not ok

    def test_effective_window_future_blocked(self, registry: RuleRegistry) -> None:
        """《增值税法》2026-01-01 前不可执行"""
        ok, reason = registry.get("VAT-EXEMPT-001").is_executable(date(2025, 12, 31))
        assert not ok and "不在生效区间" in reason

    def test_pending_refresh_blocked(self, registry: RuleRegistry) -> None:
        """省级补丁未经双人签发（pending_refresh）必须挂起"""
        ok, reason = registry.get("AGRI-DEEM-PROV-TEMPLATE").is_executable(ON_DATE)
        assert not ok and "pending_refresh" in reason

    def test_require_all_executable_atomic(self, registry: RuleRegistry) -> None:
        """批量闸门原子性：一个失效即整体不可执行"""
        with pytest.raises(RuleNotExecutableError) as exc_info:
            registry.require_all_executable(
                ["AGRI-DEEM-001", "VAT-RATE-LEGACY-001"], ON_DATE
            )
        assert exc_info.value.rule_id == "VAT-RATE-LEGACY-001"

    def test_snapshot_triple_shape(self, registry: RuleRegistry) -> None:
        """审计证据链第3步三元组：Rule ID + 文号 + 生效状态"""
        snap = registry.snapshot_triple("AGRI-DEEM-001", ON_DATE)
        assert snap["rule_id"] == "AGRI-DEEM-001"
        assert "财税〔2012〕38号" in snap["source"]
        assert snap["status"] == "active" and snap["executable"] is True
        assert snap["effective_window"][1] == "2027-12-31"


# ── 执行器：路由与确定性 ──
class TestExecutor:
    def test_auto_route_with_calc_id(self, executor: RuleExecutor) -> None:
        """有效规则 → 自动执行，产出 calc_id 与参数快照"""
        from app.core.deemed_deduction.engine import build_rate_routing_graph
        result = executor.execute(
            rule_ids=["AGRI-DEEM-001", "AGRI-DEEM-RATE-001", "AGRI-DEEM-COF-001"],
            graph=build_rate_routing_graph(),
            context={"output_vat": 9, "in_scope": True},
            on_date=ON_DATE,
        )
        assert isinstance(result, dict) or hasattr(result, "calc_id")
        assert result.route == "auto"
        assert len(result.calc_id) == 64
        assert result.params_snapshot["engine"].startswith("zen-engine")
        # zen 图输出因 passThrough 嵌套在 result 命名空间下
        assert result.result["result"]["rate"] == 0.09

    def test_recalc_agreement_100pct(self, executor: RuleExecutor) -> None:
        """验收指标：相同输入下重算一致率 100%（calc_id 相同）"""
        from app.core.deemed_deduction.engine import build_rate_routing_graph
        args = dict(
            rule_ids=["AGRI-DEEM-001", "AGRI-DEEM-RATE-001", "AGRI-DEEM-COF-001"],
            graph=build_rate_routing_graph(),
            context={"output_vat": 9, "in_scope": True},
            on_date=ON_DATE,
        )
        r1, r2 = executor.execute(**args), executor.execute(**args)
        assert r1.calc_id == r2.calc_id
        assert r1.result == r2.result

    def test_manual_route_on_repealed(self, executor: RuleExecutor) -> None:
        """引用已废止规则 → 挂起转人工，不产生计算结果"""
        from app.core.deemed_deduction.engine import build_rate_routing_graph
        out = executor.execute(
            rule_ids=["VAT-RATE-LEGACY-001"],
            graph=build_rate_routing_graph(),
            context={"output_vat": 9, "in_scope": True},
            on_date=ON_DATE,
        )
        assert isinstance(out, ManualRoute)
        assert out.rule_id == "VAT-RATE-LEGACY-001"

    def test_out_of_scope_routes_manual(self, executor: RuleExecutor) -> None:
        """范围外产品（酸奶等）→ 引擎兜底转人工，禁止默认套用 9%"""
        from app.core.deemed_deduction.engine import build_rate_routing_graph
        result = executor.execute(
            rule_ids=["AGRI-DEEM-001", "AGRI-DEEM-RATE-001", "AGRI-DEEM-COF-001"],
            graph=build_rate_routing_graph(),
            context={"output_vat": 9, "in_scope": False},
            on_date=ON_DATE,
        )
        assert result.result["result"]["route_note"].startswith("ROUTE_TO_MANUAL")
