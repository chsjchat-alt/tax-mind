"""
通用 Schemas

分页参数和统一列表响应。
"""
from typing import Any

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")


class PaginatedResponse(BaseModel):
    """通用分页响应"""
    items: list = Field(default_factory=list)
    total: int = Field(default=0)
    page: int = Field(default=1)
    page_size: int = Field(default=20)
    total_pages: int = Field(default=0)
