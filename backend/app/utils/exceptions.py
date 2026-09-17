"""
自定义异常类
"""
from fastapi import HTTPException


class AppException(Exception):
    """蒙牛全产业链 AI 内生合规决策大脑基础异常"""
    def __init__(self, code: int = 50000, message: str = "服务器内部错误"):
        self.code = code
        self.message = message
        super().__init__(message)


class DataMissingError(AppException):
    """数据缺失异常 (40001)"""
    def __init__(self, message: str = "数据缺失"):
        super().__init__(code=40001, message=message)


class ParameterError(AppException):
    """参数异常 (40002)"""
    def __init__(self, message: str = "参数异常"):
        super().__init__(code=40002, message=message)


class TaxPermissionError(AppException):
    """权限不足 (40003)"""
    def __init__(self, message: str = "权限不足"):
        super().__init__(code=40003, message=message)
