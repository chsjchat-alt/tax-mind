"""
ssf_analyzer 单元测试

覆盖：
  - 四个纯函数：_compute_power_coord / _compute_trust_coord /
    _determine_quadrant / _build_movement_description 全部分支
  - async analyze_ssf_state：无风险评估、无画像、有画像、历史轨迹、
    前一象限判定
  - async analyze_all_enterprises_ssf：成功路径与异常兜底路径
"""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, patch

from app.core.ssf_analyzer import (
    _compute_power_coord,
    _compute_trust_coord,
    _determine_quadrant,
    _build_movement_description,
    analyze_ssf_state,
    analyze_all_enterprises_ssf,
    SSFState,
    SSFResult,
)


# ═══════════════════════════════════════════
# 纯函数
# ═══════════════════════════════════════════

class TestComputePowerCoord:
    def test_mid_score(self):
        assert _compute_power_coord("medium", 80.0) == 80.0

    def test_clamp_upper(self):
        assert _compute_power_coord("critical", 120.0) == 100.0

    def test_clamp_lower(self):
        assert _compute_power_coord("low", -10.0) == 0.0

    def test_center_value(self):
        assert _compute_power_coord("low", 50.0) == 50.0


class TestComputeTrustCoord:
    def test_none_defaults_neutral(self):
        assert _compute_trust_coord(None) == 50.0

    def test_normal_deviation(self):
        assert _compute_trust_coord(30.0) == 70.0

    def test_deviation_zero(self):
        assert _compute_trust_coord(0.0) == 100.0

    def test_deviation_beyond_100_clamps_zero(self):
        assert _compute_trust_coord(150.0) == 0.0

    def test_negative_deviation_clamps_100(self):
        assert _compute_trust_coord(-20.0) == 100.0


class TestDetermineQuadrant:
    @pytest.mark.parametrize("power,trust,expected", [
        (80.0, 80.0, "I"),
        (80.0, 20.0, "II"),
        (20.0, 20.0, "III"),
        (20.0, 80.0, "IV"),
        (50.0, 50.0, "I"),      # 中心线归入 I（>= 判定）
        (50.0, 49.9, "II"),
        (49.9, 50.0, "IV"),
    ])
    def test_quadrants(self, power, trust, expected):
        assert _determine_quadrant(power, trust) == expected


class TestBuildMovementDescription:
    def test_no_previous_stable(self):
        assert _build_movement_description("I", None) == "状态稳定，保持在当前象限"

    def test_same_quadrant_stable(self):
        assert _build_movement_description("II", "II") == "状态稳定，保持在当前象限"

    @pytest.mark.parametrize("prev,curr,keyword", [
        ("III", "II", "恢复"),
        ("III", "I", "重大合规突破"),
        ("III", "IV", "信任正在重建"),
        ("II", "I", "侥幸心理已破除"),
        ("II", "IV", "权力威慑减弱"),
        ("IV", "I", "权力感知增强"),
    ])
    def test_improvements(self, prev, curr, keyword):
        assert keyword in _build_movement_description(curr, prev)

    @pytest.mark.parametrize("prev,curr,keyword", [
        ("I", "II", "信任下降"),
        ("I", "IV", "权力威慑弱化"),
        ("I", "III", "严重退化"),
        ("II", "III", "陷入放弃状态"),
        ("IV", "III", "信任崩塌"),
    ])
    def test_deteriorations(self, prev, curr, keyword):
        assert keyword in _build_movement_description(curr, prev)

    def test_unknown_movement_generic(self):
        # (prev=IV, curr=II) 不在改善/恶化映射表中 → 通用描述
        assert _build_movement_description("II", "IV") == "象限移动: IV → II"


# ═══════════════════════════════════════════
# analyze_ssf_state（伪造 AsyncSession）
# ═══════════════════════════════════════════

class _FakeProfile:
    def __init__(self, deviation_index, created_at=None):
        self.deviation_index = deviation_index
        self.created_at = created_at or datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeRA:
    def __init__(self, score):
        self.overall_risk_score = score


class _FakeScalarResult:
    def __init__(self, *, scalars=None, one=None):
        self._scalars = scalars or []
        self._one = one

    def scalars(self):
        return self

    def all(self):
        return list(self._scalars)

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    async def execute(self, query):
        self.calls.append(query)
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_analyze_no_data_uses_defaults():
    """无风险评估且无心理画像 → 默认权力 50、中性信任 50、象限 I"""
    db = _FakeDB([
        _FakeScalarResult(one=None),   # 风险评估（无）
        _FakeScalarResult(one=None),   # 心理画像（无）
        _FakeScalarResult(scalars=[]),  # 历史画像
        _FakeScalarResult(scalars=[]),  # 历史风险评估
    ])
    with patch(
        "app.core.ssf_analyzer.compute_compliance_adjusted_risk",
        new=AsyncMock(return_value={
            "adjusted_score": 80.0, "adjusted_level": "high", "reduction_pct": 0.2,
        }),
    ):
        result = await analyze_ssf_state(db, "ent-1", "测试企业")

    state = result.current_state
    assert state.enterprise_id == "ent-1"
    assert state.power_coord == 80.0
    assert state.trust_coord == 50.0
    assert state.quadrant == "I"
    assert state.trust_source == "无心理画像数据，使用默认中性值"
    assert state.previous_quadrant is None
    assert state.movement_description == "状态稳定，保持在当前象限"
    assert result.history == []


@pytest.mark.asyncio
async def test_analyze_with_profile_adjusts_trust():
    """有风险评估与画像 → 信任坐标按 reduction_pct 调整"""
    db = _FakeDB([
        _FakeScalarResult(one=_FakeRA(90.0)),
        _FakeScalarResult(one=_FakeProfile(30.0)),
        _FakeScalarResult(scalars=[]),
        _FakeScalarResult(scalars=[]),
    ])
    with patch(
        "app.core.ssf_analyzer.compute_compliance_adjusted_risk",
        new=AsyncMock(return_value={
            "adjusted_score": 85.0, "adjusted_level": "high", "reduction_pct": 0.2,
        }),
    ):
        result = await analyze_ssf_state(db, "ent-1")

    state = result.current_state
    assert state.power_coord == 85.0
    # adjusted_deviation = 30 * (1 - 0.2*0.5) = 27 → trust = 73
    assert state.trust_coord == 73.0
    assert state.quadrant == "I"
    assert "30.0" in state.trust_source
    assert state.adjusted_risk_score == 85.0
    assert len(db.calls) == 4


@pytest.mark.asyncio
async def test_analyze_history_and_previous_quadrant():
    """两条历史画像 → 上一象限取自倒数第二条，移动描述为改善"""
    old = _FakeProfile(80.0, datetime(2025, 1, 1, tzinfo=timezone.utc))
    new = _FakeProfile(10.0, datetime(2026, 1, 1, tzinfo=timezone.utc))
    db = _FakeDB([
        _FakeScalarResult(one=_FakeRA(90.0)),
        _FakeScalarResult(one=new),                  # 最新画像
        _FakeScalarResult(scalars=[new, old]),       # 历史画像（desc：新在前）
        _FakeScalarResult(scalars=[_FakeRA(90.0), _FakeRA(10.0)]),  # 历史风险评估（desc）
    ])
    with patch(
        "app.core.ssf_analyzer.compute_compliance_adjusted_risk",
        new=AsyncMock(return_value={
            "adjusted_score": 90.0, "adjusted_level": "critical", "reduction_pct": 0.1,
        }),
    ):
        result = await analyze_ssf_state(db, "ent-1")

    # reversed([new, old]) → old 先处理：power=10、trust=20 → III
    # new：power=90、trust=90 → I
    assert len(result.history) == 2
    assert result.history[0].quadrant == "III"
    assert result.history[1].quadrant == "I"
    state = result.current_state
    assert state.previous_quadrant == "III"
    assert "重大合规突破" in state.movement_description


# ═══════════════════════════════════════════
# analyze_all_enterprises_ssf
# ═══════════════════════════════════════════

def _fake_state():
    return SSFState(
        enterprise_id="ent-1",
        enterprise_name="测试企业",
        power_coord=70.0,
        trust_coord=60.0,
        quadrant="I",
        quadrant_name="合法合规",
        quadrant_subtitle="sub",
        quadrant_color="#10B981",
        quadrant_icon="shield_check",
        npt_mix={"nudge": 0.9, "budge": 0.05, "trudge": 0.05},
        primary_strategy="nudge",
        strategy_brief="维持型助推",
        target_direction="维持",
        power_source="power",
        trust_source="trust",
        adjusted_risk_score=70.0,
        risk_trend="stable_low",
        previous_quadrant=None,
        movement_description="状态稳定",
    )


@pytest.mark.asyncio
async def test_analyze_all_success_path():
    """批量分析成功路径返回结构化摘要"""
    async def _fake(db, enterprise_id, enterprise_name=""):
        return SSFResult(current_state=_fake_state())

    with patch("app.core.ssf_analyzer.analyze_ssf_state", new=_fake):
        summaries = await analyze_all_enterprises_ssf(None, [
            {"id": "ent-1", "name": "测试企业"},
        ])

    assert len(summaries) == 1
    s = summaries[0]
    assert s["enterprise_id"] == "ent-1"
    assert s["power_coord"] == 70.0
    assert s["trust_coord"] == 60.0
    assert s["quadrant"] == "I"
    assert s["primary_strategy"] == "nudge"


@pytest.mark.asyncio
async def test_analyze_all_exception_fallback():
    """单个企业分析失败 → 兜底默认坐标且不中断批量"""
    async def _fail(db, enterprise_id, enterprise_name=""):
        raise RuntimeError("db down")

    with patch("app.core.ssf_analyzer.analyze_ssf_state", new=_fail):
        summaries = await analyze_all_enterprises_ssf(None, [
            {"id": "ent-1", "name": "企业A"},
            {"id": "ent-2", "name": "企业B"},
        ])

    assert len(summaries) == 2
    for s in summaries:
        assert s["power_coord"] == 50.0
        assert s["trust_coord"] == 50.0
        assert s["quadrant"] == "I"
        assert s["movement_description"] == "SSF分析失败"
