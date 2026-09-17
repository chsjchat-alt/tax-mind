"""
Rule ID 法规治理矩阵 · 注册表（V4 §十一的工程化落点）

职责（对应方案「LLM explains. Skill calculates. Rule Engine governs. Evidence Chain proves.」
中的 Rule Engine governs 层）：

  1. 加载并校验规则元数据（fixtures/rules.json，来源为方案 §十一 矩阵）；
  2. 按日期判定规则的时效状态（生效区间 + status）；
  3. 判定规则是否可进入自动计算路径（review 状态闸门）——
     未经人工复核签发（pending_refresh）的规则一律挂起自动计算，切流至人工审核；
  4. 为审计证据链提供「Rule ID + 法规文号 + 生效状态」三元组。

设计铁律（继承方案 V3.1 教训）：
  - 规则的时效状态（Active/Repealed/Superseded）与生效区间必须来自法规原文本身，
    不得由引擎自行推断 sunset date；
  - 注册表为纯标准库实现（无第三方依赖），保证在任何环境下可加载、可审计。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional

# ── 默认数据文件（与本项目同源分发） ──
_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "rules.json"


class RuleStatus(str, Enum):
    """时效状态：必须来自法规原文，而非引擎推断"""

    ACTIVE = "active"
    REPEALED = "repealed"          # 已废止（如 2011 年第 38 号，2026-08-10 全文废止）
    SUPERSEDED = "superseded"      # 被新文停止执行（如加计 1% 抵扣，2026-01-01 停止）
    DYNAMIC = "dynamic"            # 动态维护（省级公告补丁）


class RulePriority(str, Enum):
    """法规来源层级（六级，效力自高到低）"""

    STATUTORY_LAW = "statutory_law"                        # 法律（《增值税法》）
    STATE_COUNCIL_REGULATION = "state_council_regulation"  # 行政法规（实施条例）
    NATIONAL_ADMIN_RULE = "national_admin_rule"            # 部门规范性文件（38号文/公告）
    LOCAL_RULE = "local_rule"                              # 省级规则
    INTERNAL_CONTROL = "internal_control"                  # 企业内控阈值（非法定）
    ENGINEERING_HEURISTIC = "engineering_heuristic"        # 工程启发（如相似度算法）


class ReviewStatus(str, Enum):
    """人工复核状态：未经复核的规则不得进入自动计算路径"""

    HUMAN_VERIFIED = "human_verified"
    PENDING_REFRESH = "pending_refresh"    # 省级公告更新后挂起，待双人签发热更新
    ARCHIVED = "archived"                  # 历史失效规则存档，仅作审计追溯


@dataclass(frozen=True)
class RuleRecord:
    """单条规则元数据（不可变，保证加载后不被运行期篡改）"""

    rule_id: str
    name: str
    source: str
    priority: RulePriority
    effective_from: Optional[date]
    effective_to: Optional[date]
    status: RuleStatus
    review: ReviewStatus
    engine_placement: str
    notes: str = ""

    def is_within_effective_window(self, on_date: date) -> bool:
        """生效区间判定（区间端点闭区间；未设端点视为开放）"""
        if self.effective_from is not None and on_date < self.effective_from:
            return False
        if self.effective_to is not None and on_date > self.effective_to:
            return False
        return True

    def is_executable(self, on_date: date) -> tuple[bool, str]:
        """
        判定规则在该日期是否可进入自动计算路径。

        Returns:
            (executable, reason)：
              - (True, "active")                       —— 可自动执行；
              - (False, "route_to_manual:...")          —— 挂起自动计算，切流人工审核。
        """
        if self.status != RuleStatus.ACTIVE:
            reason = f"route_to_manual: status={self.status.value}"
            if self.review != ReviewStatus.HUMAN_VERIFIED:
                reason += f", review={self.review.value}"
            reason += f"（{self.source}）"
            return False, reason
        if not self.is_within_effective_window(on_date):
            return False, (
                f"route_to_manual: 日期 {on_date.isoformat()} 不在生效区间 "
                f"[{self.effective_from}, {self.effective_to}]"
            )
        if self.review != ReviewStatus.HUMAN_VERIFIED:
            return False, (
                f"route_to_manual: review={self.review.value}（未经人工复核签发，"
                "不得进入自动计算路径）"
            )
        return True, "active"


class RuleRegistryError(Exception):
    """注册表数据错误"""


class RuleNotExecutableError(Exception):
    """规则不可自动执行（携带 route_to_manual 语义，由上层切流人工审核）"""

    def __init__(self, rule_id: str, reason: str) -> None:
        self.rule_id = rule_id
        self.reason = reason
        super().__init__(f"规则 {rule_id} 不可自动执行：{reason}")


@dataclass
class RuleRegistry:
    """规则注册表：加载、查询、时效与复核闸门"""

    rules: dict[str, RuleRecord] = field(default_factory=dict)

    # ── 构造 ──
    @classmethod
    def load_default(cls) -> "RuleRegistry":
        """从随项目分发的 fixtures/rules.json 加载（V4 §十一矩阵数据源）"""
        return cls.load_from_file(_FIXTURE_PATH)

    @classmethod
    def load_from_file(cls, path: Path | str) -> "RuleRegistry":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        registry = cls()
        for item in raw.get("rules", []):
            record = cls._parse_rule(item)
            if record.rule_id in registry.rules:
                raise RuleRegistryError(f"规则 ID 重复：{record.rule_id}")
            registry.rules[record.rule_id] = record
        return registry

    @staticmethod
    def _parse_rule(item: dict) -> RuleRecord:
        try:
            return RuleRecord(
                rule_id=item["rule_id"],
                name=item["name"],
                source=item["source"],
                priority=RulePriority(item["priority"]),
                effective_from=(
                    date.fromisoformat(item["effective_from"])
                    if item.get("effective_from") else None
                ),
                effective_to=(
                    date.fromisoformat(item["effective_to"])
                    if item.get("effective_to") else None
                ),
                status=RuleStatus(item["status"]),
                review=ReviewStatus(item["review"]),
                engine_placement=item["engine_placement"],
                notes=item.get("notes", ""),
            )
        except (KeyError, ValueError) as exc:
            raise RuleRegistryError(f"规则数据不合法：{item.get('rule_id', '?')}：{exc}") from exc

    # ── 查询 ──
    def get(self, rule_id: str) -> RuleRecord:
        try:
            return self.rules[rule_id]
        except KeyError:
            raise RuleRegistryError(f"未知规则 ID：{rule_id}") from None

    def require_executable(self, rule_id: str, on_date: date) -> RuleRecord:
        """闸门：规则必须可自动执行，否则抛出 RuleNotExecutableError（切流人工）"""
        rule = self.get(rule_id)
        ok, reason = rule.is_executable(on_date)
        if not ok:
            raise RuleNotExecutableError(rule_id, reason)
        return rule

    def require_all_executable(self, rule_ids: list[str], on_date: date) -> list[RuleRecord]:
        """批量闸门：任一规则不可执行即整体挂起（挂起原子性）"""
        resolved: list[RuleRecord] = []
        for rid in rule_ids:
            resolved.append(self.require_executable(rid, on_date))
        return resolved

    def snapshot_triple(self, rule_id: str, on_date: date) -> dict:
        """审计证据链第 3 步：Rule ID + 法规文号 + 生效状态 三元组"""
        rule = self.get(rule_id)
        ok, reason = rule.is_executable(on_date)
        return {
            "rule_id": rule.rule_id,
            "source": rule.source,
            "effective_window": [rule.effective_from.isoformat() if rule.effective_from else None,
                                 rule.effective_to.isoformat() if rule.effective_to else None],
            "status": rule.status.value,
            "review": rule.review.value,
            "on_date": on_date.isoformat(),
            "executable": ok,
            "reason": reason,
        }
