"""
自定义异常类
"""
from fastapi import HTTPException


class TaxMindException(Exception):
    """税智·心判基础异常"""
    def __init__(self, code: int = 50000, message: str = "服务器内部错误"):
        self.code = code
        self.message = message
        super().__init__(message)


class DataMissingError(TaxMindException):
    """数据缺失异常 (40001)"""
    def __init__(self, message: str = "数据缺失"):
        super().__init__(code=40001, message=message)


class ParameterError(TaxMindException):
    """参数异常 (40002)"""
    def __init__(self, message: str = "参数异常"):
        super().__init__(code=40002, message=message)


class TaxPermissionError(TaxMindException):
    """权限不足 (40003)"""
    def __init__(self, message: str = "权限不足"):
        super().__init__(code=40003, message=message)
