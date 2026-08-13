"""
profile_service.build_behavioral_data 单元测试

聚焦整改任务完成率（remediation_completion_rate）的数据库计算逻辑：
  - 完成率 = status='completed' 的任务数 / 总任务数 * 100
  - 无任务时返回 0
  - 返回值为数字（float）

通过伪造 AsyncSession 的 execute 返回值（按调用顺序）隔离数据库依赖。
"""

import pytest

from app.services.profile_service import ProfileService


class _FakeScalarResult:
    """模拟 SQLAlchemy 结果对象（支持 scalars/scalar/scalar_one_or_none）"""

    def __init__(self, *, scalars=None, scalar=None, one=None):
        self._scalars = scalars or []
        self._scalar = scalar
        self._one = one

    def scalars(self):
        return self

    def all(self):
        return list(self._scalars)

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    """按 execute 调用顺序返回预置结果"""

    def __init__(self, results):
        self._results = list(results)

    async def execute(self, query):
        return self._results.pop(0)


class _FakeEnterprise:
    def __init__(self, eid="ent-1"):
        self.id = eid
        self.revenue_annual = 0
        self.is_high_tech = False
        self.is_small_micro = True


async def _build_with_tasks(total: int, completed: int) -> float:
    """构造含 total/completed 个整改任务的假库并调用 build_behavioral_data"""
    results = [
        _FakeScalarResult(scalars=[]),    # 1. 银行流水（空）
        _FakeScalarResult(scalar=0),      # 2. 风险记录总数
        _FakeScalarResult(scalar=0),      # 3. 高风险记录数
        _FakeScalarResult(scalar=total),  # 4. 整改任务总数
        _FakeScalarResult(scalar=completed),  # 5. 已完成整改任务数
        _FakeScalarResult(one=None),      # 6. 最新风险评估
        _FakeScalarResult(scalars=[]),    # 7. 纳税申报（空）
    ]
    db = _FakeDB(results)
    behavioral = await ProfileService.build_behavioral_data(db, _FakeEnterprise())
    return behavioral.remediation_completion_rate


@pytest.mark.asyncio
async def test_remediation_rate_partial_completed():
    """2 个任务、1 个完成 → 完成率 50.0"""
    rate = await _build_with_tasks(total=2, completed=1)
    assert rate == 50.0


@pytest.mark.asyncio
async def test_remediation_rate_all_completed():
    """4 个任务全部完成 → 完成率 100.0"""
    rate = await _build_with_tasks(total=4, completed=4)
    assert rate == 100.0


@pytest.mark.asyncio
async def test_remediation_rate_no_tasks_returns_zero():
    """无整改任务 → 完成率 0"""
    rate = await _build_with_tasks(total=0, completed=0)
    assert rate == 0.0


@pytest.mark.asyncio
async def test_remediation_rate_none_completed():
    """2 个任务、0 个完成 → 完成率 0.0"""
    rate = await _build_with_tasks(total=2, completed=0)
    assert rate == 0.0


@pytest.mark.asyncio
async def test_remediation_rate_is_number():
    """完成率返回值必须是数字（float）"""
    for total, completed in [(0, 0), (3, 1), (3, 2)]:
        rate = await _build_with_tasks(total=total, completed=completed)
        assert isinstance(rate, float), f"total={total}, completed={completed} 返回 {rate!r} 非数字"
        assert 0.0 <= rate <= 100.0
