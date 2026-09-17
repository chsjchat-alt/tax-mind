"""
Rule ID 法规治理矩阵 · zen-engine 执行适配器

依赖：zen-engine>=2.0,<2.1（MIT License，gorules/zen）。

⚠ 版本坑（实测确认，2.x 相对 1.x/0.x 的破坏性变更）：
  - 导入模块名由 zen_engine 改为 zen（PyPI 包名仍为 zen-engine）；
  - 决策图顶层为 {"nodes": [...], "edges": [...]}，边字段为 sourceId/targetId（非 source/target）；
  - 内联业务规则使用 expressionNode / decisionTableNode 节点类型；
    名为 decisionNode 的类型是「引用型」节点（content 为文档键，须经 loader 加载），
    直接内联 content 会在执行期报 “Loader is not defined”；
  - decisionTableNode.content 须含顶层 "key"（输出字段名）；
  - evaluate() 返回 dict，结果位于 ["result"]。

职责边界（对应方案铁律「税额、评分绝不交给浮点引擎计算」）：
  - zen-engine 只承担「资格判定 / 路由 / 兜底转人工」等定性规则；
  - 一切金额与税额计算由本项目 Decimal 确定性函数完成（见 deemed_deduction.engine）；
  - 本适配器为每次执行生成确定性计算 ID 与参数快照，支撑审计证据链
    （原始数据 → 规则版本 → 计算 → 计算ID+参数快照 → 复核 → 审计留痕）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from importlib import metadata as _importlib_metadata
from typing import Any, Optional

from app.core.rule_governance.rule_registry import (
    RuleNotExecutableError,
    RuleRegistry,
)

try:  # zen-engine 2.x：导入名为 zen
    from zen import ZenEngine as _ZenEngine
except ImportError as _exc:  # pragma: no cover - 环境缺失时给出明确指引
    raise ImportError(
        "缺少依赖 zen-engine（>=2.0,<2.1）。注意：2.x 起 Python 导入模块名为 zen。"
        "请执行：pip install 'zen-engine>=2.0,<2.1'"
    ) from _exc


# ── 结果与异常 ──
@dataclass(frozen=True)
class CalculationResult:
    """一次确定性规则执行的结果（含审计证据链要素）"""

    calc_id: str                       # 计算实例哈希标识（确定性，可重放）
    rule_ids: tuple[str, ...]          # 本次执行引用的规则（全部过闸门）
    graph_sha256: str                  # 决策图内容哈希（规则版本快照）
    params_snapshot: dict              # 输入参数快照（永久存盘依据）
    result: dict                       # 引擎输出（["result"]）
    route: str = "auto"                # auto=自动执行；manual=挂起转人工
    reason: str = "active"
    performance: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ManualRoute:
    """人工审核路由（挂起自动计算的原子结果）"""

    route: str = "manual"
    rule_id: str = ""
    reason: str = ""


class RuleExecutor:
    """规则执行器：闸门（registry）→ zen 决策图 → 计算ID/快照"""

    def __init__(
        self,
        registry: Optional[RuleRegistry] = None,
        engine: Optional[Any] = None,
    ) -> None:
        self.registry = registry if registry is not None else RuleRegistry.load_default()
        self._engine = engine if engine is not None else _ZenEngine()

    # ── 内部工具 ──
    @staticmethod
    def _canonical_json(payload: Any) -> str:
        """规范化 JSON（键排序、去空格），保证哈希可复现"""
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # ── 核心执行 ──
    def execute(
        self,
        rule_ids: list[str],
        graph: dict,
        context: dict,
        on_date: Optional[date] = None,
    ) -> CalculationResult | ManualRoute:
        """
        执行一次规则判定。

        Args:
            rule_ids: 本次执行引用的规则 ID 列表（先全部过注册表闸门）。
            graph:    zen-engine 2.x 决策图 {"nodes": [...], "edges": [...]}。
            context:  输入参数（业务事实）。
            on_date:  时效判定基准日（显式传入以保证可重放；缺省取系统当日）。

        Returns:
            CalculationResult（自动执行）或 ManualRoute（任一规则不可执行）。
        """
        if on_date is None:
            on_date = date.today()

        # 1) 闸门：任一规则不可执行 → 整体挂起（原子性，不产生部分计算结果）
        try:
            self.registry.require_all_executable(rule_ids, on_date)
        except RuleNotExecutableError as exc:
            return ManualRoute(rule_id=exc.rule_id, reason=exc.reason)

        # 2) 规则版本快照（图内容哈希）
        graph_json = self._canonical_json(graph)
        graph_sha = self._sha256(graph_json)

        # 3) 参数快照（决定论：规范化 JSON）
        params_snapshot = {
            "context": context,
            "rule_ids": sorted(rule_ids),
            "graph_sha256": graph_sha,
            "on_date": on_date.isoformat(),
            "engine": f"zen-engine {_importlib_metadata.version('zen-engine')}",
        }

        # 4) 执行（确定性：同图同参必同果）
        decision = self._engine.create_decision(graph_json)
        evaluated = decision.evaluate(dict(context))
        result = evaluated.get("result", {}) if isinstance(evaluated, dict) else {}

        # 5) 计算 ID（哈希要素：规则 + 图版本 + 参数快照；不含墙钟时间）
        calc_id = self._sha256(self._canonical_json(params_snapshot))

        return CalculationResult(
            calc_id=calc_id,
            rule_ids=tuple(sorted(rule_ids)),
            graph_sha256=graph_sha,
            params_snapshot=params_snapshot,
            result=result,
            performance=evaluated.get("performance", {}) if isinstance(evaluated, dict) else {},
        )
