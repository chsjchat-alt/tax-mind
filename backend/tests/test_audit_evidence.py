"""
audit_evidence（审计证据链落库助手）单元测试

覆盖 V4 §二 证据链验收口径：
  - 参数快照规范化（键排序、紧凑分隔符）→ 同输入可精确重放；
  - 证据挂载/读取语义（request.state 列表、按序、读取即清空）；
  - 防御分支（空 calc_id 忽略、列宽截断、rule_ids 补入与保留）。
"""
import json

from app.services.audit_evidence import (
    CALC_EVIDENCE_ATTR,
    attach_calc_evidence,
    canonical_snapshot,
    take_calc_evidence,
)


class _FakeState:
    """模拟 starlette request.state（属性包）"""


class _FakeRequest:
    def __init__(self):
        self.state = _FakeState()


class TestCanonicalSnapshot:
    def test_keys_sorted_and_compact(self):
        """快照 JSON：键排序 + 无空格分隔（规范化，保证可重放比对）"""
        snap = canonical_snapshot({"b": 2, "a": 1, "c": {"y": 2, "x": 1}})
        assert snap == '{"a":1,"b":2,"c":{"x":1,"y":2}}'
        # 反解后内容等价
        assert json.loads(snap) == {"a": 1, "b": 2, "c": {"x": 1, "y": 2}}

    def test_rule_ids_injected_sorted_and_deduped(self):
        """快照缺 rule_ids 时按参数补入（去重 + 排序）"""
        snap = canonical_snapshot({"q": "100"}, ["R-09", "R-01", "R-09"])
        payload = json.loads(snap)
        assert payload["rule_ids"] == ["R-01", "R-09"]

    def test_existing_rule_ids_preserved(self):
        """快照已含 rule_ids 时不被参数覆盖（引擎口径优先）"""
        snap = canonical_snapshot({"rule_ids": ["R-05"]}, ["R-01"])
        assert json.loads(snap)["rule_ids"] == ["R-05"]

    def test_empty_snapshot_still_valid_json(self):
        assert json.loads(canonical_snapshot(None)) == {}


class TestAttachAndTake:
    def test_attach_appends_in_order_and_take_clears(self):
        """多次计算按序挂载；take 读取后清空（防重复落库）"""
        req = _FakeRequest()
        attach_calc_evidence(req, calc_id="a" * 64, params_snapshot={"n": 1})
        attach_calc_evidence(req, calc_id="b" * 64, params_snapshot={"n": 2},
                             rule_ids=["R-01"], action="deemed_deduction.calculate")

        evidence = take_calc_evidence(req)
        assert len(evidence) == 2
        assert evidence[0]["calculation_id"] == "a" * 64
        assert evidence[1]["calculation_id"] == "b" * 64
        assert evidence[1]["action"] == "deemed_deduction.calculate"
        assert json.loads(evidence[1]["param_snapshot"]) == {
            "n": 2, "rule_ids": ["R-01"],
        }
        # 读取即清空
        assert take_calc_evidence(req) == []
        assert getattr(req.state, CALC_EVIDENCE_ATTR) == []

    def test_empty_calc_id_ignored(self):
        """calc_id 为空（人工路由无证据）→ 不挂载"""
        req = _FakeRequest()
        attach_calc_evidence(req, calc_id="", params_snapshot={"n": 1})
        assert take_calc_evidence(req) == []

    def test_calc_id_truncated_to_column_width(self):
        """calculation_id 列宽 String(64)：超长截断防数据库写入异常"""
        req = _FakeRequest()
        attach_calc_evidence(req, calc_id="x" * 100, params_snapshot={})
        assert take_calc_evidence(req)[0]["calculation_id"] == "x" * 64

    def test_take_on_untouched_request_returns_empty(self):
        """未挂载任何证据的请求 → 空列表（中间件安全消费）"""
        assert take_calc_evidence(_FakeRequest()) == []
