"""
Rule ID 法规治理矩阵（V4 §十一的工程化落点）

导出：注册表（时效/复核闸门）+ zen-engine 执行适配器（计算ID/参数快照）。
"""
from app.core.rule_governance.rule_registry import (
    RuleNotExecutableError,
    RulePriority,
    RuleRecord,
    RuleRegistry,
    RuleRegistryError,
    RuleStatus,
    ReviewStatus,
)
from app.core.rule_governance.rule_executor import (
    CalculationResult,
    ManualRoute,
    RuleExecutor,
)

__all__ = [
    "RuleRegistry",
    "RuleRecord",
    "RuleRegistryError",
    "RuleNotExecutableError",
    "RuleStatus",
    "RulePriority",
    "ReviewStatus",
    "RuleExecutor",
    "CalculationResult",
    "ManualRoute",
]
