"""
审计证据链落库助手（V4 §二 / §3.2 评分定义卡）

打通「确定性引擎 → 审计日志」的最后一公里：
  引擎层（rule_governance / deemed_deduction）每次确定性计算产出
  calc_id + 参数快照 → 本助手将其挂载到当前请求的 state →
  审计中间件（app/main.py）写入 audit_logs 的 calculation_id / param_snapshot 列
  （列由 alembic 009_add_audit_calc_snapshot 迁移创建）。

设计约定：
  - 业务代码不直接写审计行，仍由中间件统一落库（与既有架构一致）；
  - 同一请求多次计算：全部证据按序挂载，首条并入该请求的审计行，
    其余由中间件生成独立 CALC 行（一次请求、多条证据均可回溯）；
  - param_snapshot 为规范化 JSON（键排序），保证同输入可精确重放。

验收口径（V4 §3.2 / 双状态三级穿透）：
  相同输入参数下重算一致率 100%（calc_id 确定性，见 test_rule_governance）。
"""
from __future__ import annotations

import json
from typing import Any, Iterable

# 挂载在 request.state 上的证据列表属性名（中间件按此名读取）
CALC_EVIDENCE_ATTR = "calc_evidence"


def canonical_snapshot(params_snapshot: Any, rule_ids: Iterable[str] = ()) -> str:
    """参数快照规范化 JSON（键排序、无空格；rule_ids 缺失时补入）。"""
    payload: dict[str, Any] = dict(params_snapshot or {})
    ids = sorted(set(str(r) for r in rule_ids if r))
    if ids and "rule_ids" not in payload:
        payload["rule_ids"] = ids
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def attach_calc_evidence(
    request: Any,
    *,
    calc_id: str,
    params_snapshot: Any,
    rule_ids: Iterable[str] = (),
    action: str = "",
) -> None:
    """把一次确定性计算的证据挂到当前请求（由审计中间件统一落库）。

    Args:
        request:   FastAPI Request（端点处理函数的入参）
        calc_id:   引擎产出的确定性计算 ID（SHA-256；空值直接忽略）
        params_snapshot: 引擎产出的参数快照（dict，可含 context/rule_ids/graph_sha256 等）
        rule_ids:  本次执行引用的规则 ID（快照缺失时补入）
        action:    业务动作标识（如 "deemed_deduction.calculate"，仅注释用途）
    """
    if not calc_id:
        return
    entry = {
        "calculation_id": str(calc_id)[:64],  # 列宽 String(64)
        "param_snapshot": canonical_snapshot(params_snapshot, rule_ids),
        "action": action,
    }
    evidence_list: list[dict] = getattr(request.state, CALC_EVIDENCE_ATTR, None)
    if evidence_list is None:
        evidence_list = []
        setattr(request.state, CALC_EVIDENCE_ATTR, evidence_list)
    evidence_list.append(entry)


def take_calc_evidence(request: Any) -> list[dict]:
    """读取并清空请求上挂载的证据列表（供中间件消费）。"""
    evidence_list: list[dict] = getattr(request.state, CALC_EVIDENCE_ATTR, None)
    if evidence_list:
        setattr(request.state, CALC_EVIDENCE_ATTR, [])
    return evidence_list or []
