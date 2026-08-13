"""大模型辅助 API Schemas"""
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """AI 对话请求"""
    messages: list[dict] = Field(..., min_length=1, description="对话消息列表")
    model: str = Field(default="deepseek", description="模型名称 deepseek/qwen")


class ChatResponse(BaseModel):
    reply: str
    model: str


class PolishReportRequest(BaseModel):
    """报告话术润色请求"""
    raw_text: str = Field(..., min_length=1, description="原始报告文本")
    context: dict = Field(default_factory=dict, description="上下文信息")
    style: str = Field(default="professional", description="风格 professional/friendly/warning")


class PolishReportResponse(BaseModel):
    polished_text: str
    changes_summary: str
