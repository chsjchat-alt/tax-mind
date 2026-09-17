"""
大模型服务封装（Mock版本）

重要：
  - 原型阶段所有LLM调用均为Mock实现
  - 核心财税逻辑（四流匹配/罚款计算/税收优惠核验/风险定级）
    使用规则引擎硬编码，绝不依赖大模型
  - 大模型仅用于非精确计算场景：报告话术润色、案例检索辅助、用户问答交互
  - 真实大模型调用作为产品化阶段的扩展功能
  - 超时30秒，重试最多3次（骨架已预留，产品化阶段激活）
"""
import asyncio
import random
from app.config import get_settings

settings = get_settings()

# ── 产品化阶段配置（原型阶段不使用） ──
LLM_TIMEOUT = 30          # 请求超时（秒）
LLM_MAX_RETRIES = 3       # 最大重试次数
LLM_RETRY_DELAY = 1.0     # 重试间隔（秒）


class LLMService:
    """
    大模型服务封装（Mock实现）

    产品化阶段需替换为真实的 DeepSeek/Qwen API 调用。
    超时和重试机制在原型阶段已预留接口，产品化阶段激活即可。
    """

    ALLOWED_MODELS = {"deepseek", "qwen"}

    # ══════════════════════════════════════════════════
    # Mock 回复模板
    # ══════════════════════════════════════════════════
    _MOCK_CHAT_REPLIES = [
        "根据您的企业数据分析，当前主要风险点集中在资金流与发票流的匹配度偏低。建议您优先关注以下方面：(1)规范发票管理，确保进销项品名与实际业务一致；(2)减少私卡收款比例，将经营性收入纳入对公账户管理。",
        "从财税合规角度看，您当前的税负率处于行业合理范围内。不过需要注意的是，税负率过低可能引发税务机关的关注，建议保持税负率在行业均值的±20%区间内。",
        "针对您提出的税务筹划问题，建议重点关注以下几点：(1)合理利用小微企业税收优惠政策；(2)规范成本费用抵扣凭证管理；(3)建立健全的财务内控制度。具体方案需要结合您的实际经营情况进行定制化设计。",
        "根据最新的税收政策，小微企业可以享受以下优惠：(1)年应纳税所得额不超过300万元的部分，减按25%计入应纳税所得额；(2)增值税小规模纳税人适用3%征收率的应税销售收入，减按1%征收。建议您及时确认企业是否符合上述条件。",
    ]

    # ══════════════════════════════════════════════════
    # 产品化阶段：超时+重试骨架
    # ══════════════════════════════════════════════════

    async def _call_with_retry(self, func, *args, **kwargs):
        """带超时和重试的函数调用（产品化阶段激活）"""
        last_error = None
        for attempt in range(LLM_MAX_RETRIES):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=LLM_TIMEOUT,
                )
            except asyncio.TimeoutError:
                last_error = f"请求超时 ({LLM_TIMEOUT}s)"
                if attempt < LLM_MAX_RETRIES - 1:
                    await asyncio.sleep(LLM_RETRY_DELAY * (attempt + 1))
            except Exception as e:
                last_error = str(e)
                if attempt < LLM_MAX_RETRIES - 1:
                    await asyncio.sleep(LLM_RETRY_DELAY * (attempt + 1))
        raise TimeoutError(f"LLM调用失败，已重试{LLM_MAX_RETRIES}次: {last_error}")

    async def chat(self, messages: list[dict], model: str = "deepseek") -> str:
        """
        Mock大模型对话

        Args:
            messages: 对话消息列表 [{"role": "user/assistant", "content": "..."}]
            model: 模型名称（deepseek/qwen），原型阶段忽略

        Returns:
            Mock回复文本

        产品化阶段替换：
            await self._call_with_retry(self._real_chat, messages, model)
        """
        if model not in self.ALLOWED_MODELS:
            model = settings.llm_provider

        # Mock: 返回随机预设回复
        return random.choice(self._MOCK_CHAT_REPLIES)

    async def polish_text(self, raw_text: str, context: dict, style: str = "professional") -> str:
        """
        Mock话术润色

        Args:
            raw_text: 原始报告文本
            context: 上下文信息
            style: 报告风格（professional/friendly/warning）

        Returns:
            原文（原型阶段不做修改）

        产品化阶段替换：
            return await self._call_with_retry(self._real_polish, raw_text, context, style)
        """
        # 原型阶段：返回原文不做修改
        return raw_text

    async def search_cases(self, industry: str, risk_type: str) -> list[dict]:
        """
        Mock案例检索

        Args:
            industry: 行业
            risk_type: 风险类型

        Returns:
            案例列表（来自 case_studies.json 的本地检索）

        说明：案例检索始终使用本地JSON，不依赖大模型。
        """
        import json
        from pathlib import Path

        cases_path = Path(__file__).parent.parent / "data" / "case_studies.json"
        try:
            with open(cases_path, "r", encoding="utf-8") as f:
                all_cases = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

        results = []
        for case in all_cases:
            if industry and case.get("industry") != industry:
                continue
            if risk_type and case.get("risk_level") != risk_type:
                continue
            results.append(case)
            if len(results) >= 5:
                break
        return results


# 单例
llm_service = LLMService()
