"""
运行时 PII 脱敏工具

特性：
  - 日志过滤器：自动替换日志中的 PII 为 [REDACTED]
  - API 响应脱敏：递归扫描 dict/list 中的敏感字段并掩码
  - 可配置脱敏字段集合和掩码策略

用法:
    from app.utils.pii import PIIMasker, mask_log, sanitize_response

    # 日志脱敏
    logger.info(mask_log(f"用户 {phone} 登录"))  # → "用户 138****1234 登录"

    # 响应脱敏（在响应返回前）
    sanitized = sanitize_response(response_data)
"""
import re
import copy
import logging
from typing import Any


# ── 敏感字段名集合 ──────────────────────────────────────
_SENSITIVE_FIELDS: set[str] = {
    "password", "hashed_password", "secret", "token",
    "access_token", "refresh_token", "api_key",
    "credit_code", "tax_id", "id_number",
    "phone", "mobile", "phone_number",
    "email", "mail",
    "full_name", "name", "account_holder",
    "bank_account", "bank_card",
}

# ── PII 模式（正则捕获常见 PII 格式） ───────────────────
_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 中国大陆手机号（11位 1 开头）
    (re.compile(r"\b(1[3-9]\d)\d{4}(\d{4})\b"), r"\1****\2"),
    # 身份证号（18位 / 17位+X）
    (re.compile(r"\b(\d{6})\d{8}(\d{3}[0-9Xx])\b"), r"\1********\2"),
    # 银行卡号（16-19位）
    (re.compile(r"\b(\d{4})\d{8,11}(\d{4})\b"), r"\1****\2"),
    # Email 地址
    (re.compile(r"\b([a-zA-Z0-9._%+-]{1,3})[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"), r"\1***@\2"),
]


def mask_log(message: str) -> str:
    """对日志消息中的 PII 进行脱敏。"""
    result = message
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _mask_value(value: Any) -> Any:
    """对单个值进行掩码"""
    if isinstance(value, str):
        if len(value) <= 2:
            return "*" * len(value)
        if len(value) <= 6:
            return value[0] + "*" * (len(value) - 1)
        # 保留首尾各 2 个字符
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    return "***"


def sanitize_response(data: Any, depth: int = 0) -> Any:
    """
    递归脱敏 API 响应数据中的敏感字段。

    Args:
        data: 待脱敏的数据（dict / list / 标量）
        depth: 递归深度保护（最大 10 层）

    Returns:
        脱敏后的数据副本（不修改原数据）
    """
    if depth > 10:
        return data

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower().replace("_", "")
            if key_lower in _SENSITIVE_FIELDS or any(
                kw in key_lower for kw in ("password", "secret", "token", "key")
            ):
                result[key] = _mask_value(value)
            elif isinstance(value, (dict, list)):
                result[key] = sanitize_response(value, depth + 1)
            else:
                result[key] = value
        return result

    if isinstance(data, list):
        return [sanitize_response(item, depth + 1) for item in data]

    return data


class PIILogFilter(logging.Filter):
    """Python logging Filter：自动对日志消息脱敏"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_log(record.msg)
        if record.args:
            # 对格式化参数中的字符串也脱敏
            new_args = tuple(
                mask_log(a) if isinstance(a, str) else a
                for a in record.args
            )
            record.args = new_args
        return True
