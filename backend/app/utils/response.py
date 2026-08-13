"""
统一响应格式

所有API返回统一结构：
  - 成功: {"code": 200, "message": "success", "data": {...}}
  - 失败: {"code": 40001/40002/40003/50000, "message": "...", "data": null}

错误码定义：
  - 200:   成功
  - 40001: 数据缺失（资源不存在/空结果集）
  - 40002: 参数异常（校验失败/字段类型错误）
  - 40003: 权限不足（未登录/无操作权限，预留）
  - 50000: 服务器内部错误（未捕获异常）
"""
from typing import Any


def success_response(data: Any = None, message: str = "success") -> dict[str, Any]:
    """构建成功响应"""
    return {"code": 200, "message": message, "data": data}


def error_response(code: int, message: str) -> dict[str, Any]:
    """构建错误响应"""
    return {"code": code, "message": message, "data": None}
