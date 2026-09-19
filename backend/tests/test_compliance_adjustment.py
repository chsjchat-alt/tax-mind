"""
compliance_adjustment（统一算分引擎）一致性单元测试

覆盖审计结论（统一收口后的防回归门禁）：
  #2  一票否决（纳税信用 D 级 / 涉税犯罪）优先于"完全合规强制 LOW"，
     顺序已固化：veto → 不降分、is_fully_compliant=False；
  #4  批量版 compute_compliance_adjusted_risks 与单条版
     compute_compliance_adjusted_risk 同输入必同输出（消除列表/详情口径分歧）；
  序列化层约束：返回结构 original_score+original_level 与
     adjusted_score+adjusted_level 天然成对，杜绝"adjusted_level + original_score"交叉绑定。
"""
import pytest

from app.core.compliance_adjustment import (
    compute_compliance_adjusted_risk,
    compute_compliance_adjusted_risks,
)
from app.models.enterprise import Enterprise, IndustryType
from app.models.remediation_task import RemediationTask, TaskStatus


# ── 轻量 Fake DB（按 execute 调用顺序弹出预置结果，隔离真实数据库）──
class _FakeResult:
    def __init__(self, one=None, rows=()):
        self._one = one
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return _FakeScalars(self._rows)

    def all(self):
        return list(self._rows)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, *_a, **_kw):
        if not self._results:
            raise AssertionError("execute 调用次数超出预置结果数")
        return self._results.pop(0)


def _make_enterprise(credit_level: str | None = None, crime: bool = False) -> Enterprise:
    return Enterprise(
        id="e1", tenant_id="t1", name="测试企业",
        credit_code="91330100MA00000001",
        industry=IndustryType.WHOLESALE_RETAIL,
        tax_credit_level=credit_level,
        tax_crime_convicted=crime,
    )


def _make_completed_task() -> RemediationTask:
    return RemediationTask(
        id="t1", enterprise_id="e1",
        status=TaskStatus.COMPLETED, source="compliance",
    )


def _base_db(
    enterprise: Enterprise | None = None,
    completed_count: int = 0,
) -> _FakeDB:
    """单条版 execute 顺序：Enterprise → risk_config → RemediationTask。"""
    return _FakeDB([
        _FakeResult(one=enterprise or _make_enterprise()),
        _FakeResult(rows=[]),  # risk_config 无覆盖，回退默认阈值 80/60/45/30
        _FakeResult(rows=[_make_completed_task() for _ in range(completed_count)]),
    ])


@pytest.mark.asyncio
class TestComputeComplianceAdjustedRisk:
    async def test_fully_compliant_forces_low(self):
        """完全合规（0 发现）→ 强制 10 分 / LOW；原始分 70 → high"""
        result = await compute_compliance_adjusted_risk(
            _base_db(), "e1", base_score=70.0, compliance_findings_count=0,
        )
        assert result["is_fully_compliant"] is True
        assert result["adjusted_score"] == 10.0
        assert result["adjusted_level"] == "low"
        assert result["original_score"] == 70.0
        assert result["original_level"] == "high"

    async def test_veto_overrides_fully_compliant(self):
        """#2 顺序固化：D 级一票否决 优先于 完全合规 → 不降分、is_fully_compliant=False"""
        result = await compute_compliance_adjusted_risk(
            _base_db(enterprise=_make_enterprise(credit_level="D"), completed_count=2),
            "e1", base_score=70.0, compliance_findings_count=0,
        )
        assert result["veto_reason"] is not None
        assert result["is_fully_compliant"] is False
        assert result["adjusted_score"] == 70.0        # 一票否决 → 修复加分不计，保持原始分
        assert result["adjusted_level"] == "high"      # 70 分 → high
        # V4 §3.2 评分定义卡：否决条件为真 → 最终状态直接判 DISQUALIFIED，不参与等级映射
        assert result["is_disqualified"] is True
        assert result["final_status"] == "DISQUALIFIED"

    async def test_final_status_follows_adjusted_level_without_veto(self):
        """未触发否决 → 最终状态 = 五档等级映射(调整后分)，is_disqualified=False"""
        result = await compute_compliance_adjusted_risk(
            _base_db(completed_count=3),
            "e1", base_score=80.0, compliance_findings_count=3,
        )
        assert result["veto_reason"] is None
        assert result["is_disqualified"] is False
        assert result["final_status"] == result["adjusted_level"] == "medium"

    async def test_remediation_reduction(self):
        """整改降分：3 个任务 → reduction 0.45 → 80*0.55=44 → medium"""
        result = await compute_compliance_adjusted_risk(
            _base_db(completed_count=3),
            "e1", base_score=80.0, compliance_findings_count=3,
        )
        assert result["original_level"] == "critical"  # 80 ≥ critical 阈值
        assert result["reduction_pct"] == 0.45
        assert result["adjusted_score"] == 44.0
        assert result["adjusted_level"] == "medium"    # 44 < 45 → medium（非 medium_high）
        assert result["completion_count"] == 3

    async def test_returned_fields_are_paired(self):
        """序列化层约束：original 与 adjusted 各自 score+level 成对返回（五级枚举）"""
        result = await compute_compliance_adjusted_risk(
            _base_db(completed_count=2),
            "e1", base_score=72.0, compliance_findings_count=2,
        )
        assert "original_score" in result and "original_level" in result
        assert "adjusted_score" in result and "adjusted_level" in result
        assert result["original_level"] in {"low", "medium", "medium_high", "high", "critical"}
        assert result["adjusted_level"] in {"low", "medium", "medium_high", "high", "critical"}
        # 未传参时兜底取数：base_score=None → 自动查最新评估（此处 FakeDB 无评估 → 100）
        fallback = await compute_compliance_adjusted_risk(
            _FakeDB([
                _FakeResult(one=_make_enterprise()),
                _FakeResult(rows=[]),                # risk_config
                _FakeResult(one=None),               # 0.6 兜底：最新 RiskAssessment 查询
                _FakeResult(rows=[]),                # 无已完成整改任务
            ]),
            "e1",
        )
        assert fallback["original_score"] == 100.0  # 兜底无数据 → 保守 100 起算
        assert fallback["adjusted_score"] == 100.0

    async def test_medium_vs_medium_high_boundary(self):
        """五级阈值边界：44 → medium，45 → medium_high"""
        low = await compute_compliance_adjusted_risk(
            _base_db(), "e1", base_score=44.0, compliance_findings_count=3,
        )
        assert low["original_level"] == "medium"
        high = await compute_compliance_adjusted_risk(
            _base_db(), "e1", base_score=45.0, compliance_findings_count=3,
        )
        assert high["original_level"] == "medium_high"


@pytest.mark.asyncio
class TestBatchMatchesSingle:
    async def test_batch_equals_single(self):
        """#4 批量版与单条版同输入必同输出（列表/详情口径一致）"""
        single = await compute_compliance_adjusted_risk(
            _base_db(completed_count=3),
            "e1", base_score=80.0, compliance_findings_count=3,
        )

        batch_db = _FakeDB([
            _FakeResult(rows=[_make_enterprise()]),   # Enterprise.in_
            _FakeResult(rows=[]),                     # risk_config
            _FakeResult(rows=[("e1", 3)]),            # group_by 计数
        ])
        batch = await compute_compliance_adjusted_risks(
            batch_db, ["e1"],
            compliance_findings_counts={"e1": 3},
            base_scores={"e1": 80.0},
        )
        assert "e1" in batch
        batch_e1 = batch["e1"]
        for key in (
            "original_score", "original_level",
            "adjusted_score", "adjusted_level",
            "final_status", "is_disqualified",
            "completion_count", "is_fully_compliant", "reduction_pct",
        ):
            assert single[key] == batch_e1[key], f"批量/单条口径分歧字段: {key}"

    async def test_batch_veto_marks_disqualified(self):
        """批量版同样遵守 V4 §3.2：D 级企业 → final_status=DISQUALIFIED"""
        batch_db = _FakeDB([
            _FakeResult(rows=[_make_enterprise(credit_level="D")]),  # Enterprise.in_
            _FakeResult(rows=[]),                                     # risk_config
            _FakeResult(rows=[("e1", 2)]),                            # group_by 计数
        ])
        batch = await compute_compliance_adjusted_risks(
            batch_db, ["e1"],
            compliance_findings_counts={"e1": 0},
            base_scores={"e1": 70.0},
        )
        e1 = batch["e1"]
        assert e1["veto_reason"] is not None
        assert e1["is_disqualified"] is True
        assert e1["final_status"] == "DISQUALIFIED"
        assert e1["adjusted_score"] == 70.0  # 否决 → 整改加分不计
