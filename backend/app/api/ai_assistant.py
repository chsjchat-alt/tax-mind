"""
大模型辅助 API（Mock版本）

POST /api/v1/ai/chat              AI问答（大模型对话）
POST /api/v1/ai/polish-report     报告话术润色

原型阶段说明：
  - 核心财税逻辑（四流匹配/罚款计算/税收优惠核验/风险定级）
    使用规则引擎硬编码，绝不依赖大模型
  - 大模型仅用于非精确计算场景：报告话术润色、用户问答交互
  - 原型阶段采用Mock实现，chat返回预设文本，polish返回原文不做修改
  - 真实大模型调用（DeepSeek/Qwen API）作为产品化阶段的扩展功能
"""
from fastapi import APIRouter, Depends

from app.api.deps import success_response, error_response, require_viewer
from app.models.user import User
from app.services.llm_service import llm_service
from app.schemas.ai_assistant import (
    ChatRequest, ChatResponse,
    PolishReportRequest, PolishReportResponse,
)

router = APIRouter(prefix="/ai", tags=["AI助手"])


@router.post("/chat")
async def ai_chat(
    request: ChatRequest,
    _user: User = Depends(require_viewer),
):
    """
    AI问答

    原型阶段Mock实现：
      - 不调用真实大模型API
      - 返回预设的专业回复文本
      - 调用方式与产品化阶段完全一致（接口不变）
    """
    if not request.messages:
        return error_response(40002, "消息列表不能为空")

    reply = await llm_service.chat(request.messages, model=request.model)

    return success_response(ChatResponse(
        reply=reply,
        model=f"{request.model} (mock)",
    ).model_dump())


@router.post("/polish-report")
async def polish_report(
    request: PolishReportRequest,
    _user: User = Depends(require_viewer),
):
    """
    报告话术润色

    原型阶段Mock实现：
      - 返回原文不做修改
      - 产品化阶段：调用大模型API进行专业话术润色
    """
    if not request.raw_text.strip():
        return error_response(40002, "报告文本不能为空")

    polished = await llm_service.polish_text(
        request.raw_text,
        context=request.context,
        style=request.style,
    )

    return success_response(PolishReportResponse(
        polished_text=polished,
        changes_summary="原型阶段：返回原文未做修改。产品化阶段将调用大模型进行专业润色。",
    ).model_dump())
