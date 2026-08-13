"""
NBT 三层行为干预大模型服务 (llm_intervention_service.py)

封装对 DeepSeek / 通义千问（Qwen）大语言模型的异步调用，
生成「Nudge-Budge-Trudge」三层结构化的行为干预内容。

核心方法：
  generate_nbt_intervention(risk_data_json) → NBTInterventionResponse

技术特性：
  - 异步 HTTP 调用（httpx）
  - 30秒超时限制
  - 最多3次指数退避重试
  - Pydantic 严格校验 LLM 返回的 JSON 结构
  - 详细的调用日志

产品化说明：
  - 原型阶段内置 LLM 输出降级策略（Mock fallback）
  - 大模型 API Key 通过 Settings 环境变量注入
  - 严禁在核心财税计算（四流匹配/罚款/税负率）中使用大模型

API 端点：
  - DeepSeek:  https://api.deepseek.com/v1/chat/completions
  - Qwen:     https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.schemas.nbt_intervention import (
    NBTInterventionResponse,
    NudgeLayer,
    BridgeLayer,
    TrudgeLayer,
)

logger = logging.getLogger("llm_intervention")

settings = get_settings()

# ── 大模型 API 端点 ──
LLM_ENDPOINTS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
}

# ── 超时与重试 ──
LLM_TIMEOUT_SEC: float = 30.0
LLM_MAX_RETRIES: int = 3
LLM_RETRY_BASE_DELAY: float = 1.5  # 指数退避基值（秒）

# ── 模型名称 ──
MODEL_NAMES: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
}

# ── 输出 token 上限 ──
MAX_OUTPUT_TOKENS: int = 4096
TEMPERATURE: float = 0.3  # 低温度以保证结构化输出


# ═══════════════════════════════════════════════════════
# NBT 系统 Prompt 模板
# ═══════════════════════════════════════════════════════

NBT_SYSTEM_PROMPT_TEMPLATE = """你是一位资深的税务行为心理学干预专家，精通「前景理论（Prospect Theory）」、
「Slope Framework（SSF）」和「NBT（Nudge-Budge-Trudge）」三层行为干预模型。

根据传入的风险 JSON 数据包（包含：轻资产属性标识、成本费用率畸高超同行200%的极值预警、
涉嫌虚增咨询费记录、预测个税穿透补缴金额、3.5倍罚款本金、日万分之五累加的18.25%年化
滞纳金总额），针对一位呈现显著「控制错觉」与「盲目乐观」偏差的企业主，严格分为三层输出。

## 输出格式要求

你必须严格按照以下 JSON 结构输出，不要添加任何 Markdown 代码块标记，不要添加额外解释：

{
  "nudge": {
    "risk_statement": "...",
    "psychological_trigger": "...",
    "visual_recommendation": "..."
  },
  "budge": {
    "loss_comparison": "...",
    "rebuttal_narrative": "...",
    "timeline_pressure": "..."
  },
  "trudge": {
    "sop_title": "...",
    "micro_tasks": [
      {
        "task_id": 1,
        "task_name": "...",
        "action": "...",
        "deadline": "...",
        "evidence_required": "..."
      }
    ],
    "compliance_framework": "...",
    "trust_building_closing": "..."
  }
}

## 当前风险数据

{risk_data_json}

## 各层写作指引

### 1. Nudge 层（环境助推）
- 利用色彩心理学语境与数据，直击「轻资产缺合法进项导致利润虚高」的固有行业痛点
- 使用诸如「稽查概率达94%」的无感陈述，引起直觉警觉
- 打破认知污泥（cognitive sludge），让企业主从"不会查到我"切换到"下一个就是我"
- risk_statement ≥ 50 字，psychological_trigger ≥ 30 字，visual_recommendation ≥ 20 字

### 2. Bridge 层（信念重塑 - 核心）
- 深度应用前景理论的损失框架（Loss Framing）
- 重点将未来三年内叠加了行政处罚与单利复现滞纳金的复合稽查预期损失总额，
  与当期立刻合规自查的「零罚款」整改成本进行强烈的、戏剧化的并列对比
- 彻底粉碎其「大不了注销破产」的逃避心理
- loss_comparison ≥ 100 字，rebuttal_narrative ≥ 50 字，timeline_pressure ≥ 30 字

### 3. Trudge 层（长效信任建设）
- 语气转为克制且专业的同理心辅导
- 依据国税发[2009]90号《大企业税务风险管理指引》的框架要求
- 针对上述暴露的内控缺陷，自动生成轻量化整改 SOP 微任务列表（3-6 项）
- 将庞大的合规工程拆解为可供界面打卡的行动指南
- sop_title ≥ 10 字，compliance_framework ≥ 50 字，trust_building_closing ≥ 30 字
- 每条 micro_task 必须包含 task_id/task_name/action/deadline/evidence_required

## 特别注意

- 所有金额数字必须与输入数据完全一致，不得四舍五入或修改
- 保持专业、克制的语调，不要使用威胁性语言
- 以建设性合作伙伴的姿态收尾，强调合规修复的信誉价值
- 仅输出 JSON，不要包含 ```json ``` 代码块标记"""


# ═══════════════════════════════════════════════════════
# Mock 降级输出
# ═══════════════════════════════════════════════════════

_MOCK_NBT_RESPONSE: dict[str, Any] = {
    "nudge": {
        "risk_statement": (
            "根据金税四期数据分析，贵司作为轻资产企业，成本费用率达行业基准的"
            "200%，存在严重的合规风险敞口。税智·心判系统评估显示，该类企业在"
            "未来12个月内被列为税务稽查对象的概率高达94%。轻资产行业固有的"
            "'缺合法进项导致利润虚高'特征，在贵司体现尤为突出，正在触发风控"
            "系统的红色预警阈值。"
        ),
        "psychological_trigger": (
            "您可能认为'风险可控，大不了补缴税款即可'——这正是典型的控制错觉"
            "与盲目乐观偏差。实际上，一旦触发税务稽查，您将失去对后续处理的"
            "主动权，滞纳金按日万分之五累积，连带的个人征信和企业评级的"
            "损害将是不可逆的。"
        ),
        "visual_recommendation": (
            "建议界面采用深红色渐变至橙色的视觉层级：风险概览区使用#DC2626"  # hex color
            "红色表示稽查概率94%，损失对比区使用#EA580C橙色，整改路径区使用"
            "#16A34A绿色表示合规修复方向。"
        ),
    },
    "budge": {
        "loss_comparison": (
            "【不行动方案】如果选择观望等待，未来三年您将面临："
            "欠税本金 + 3.5倍行政罚款（征管法第63条）+ 日万分之五滞纳金"
            "× 1095天（三年累计18.25%年化）= 超过¥{total_exposure}的复合损失。"
            "此外，法人代表将被限制高消费，企业纳税信用等级降至D级，"
            "银行授信额度归零。"
            "【立刻行动方案】如果今天开始合规自查：零罚款（自查补税免于处罚），"
            "仅需补缴欠税本金¥{principal}，滞纳金从整改完成之日停止计算。"
            "两种方案之间的差距是¥{gap}——这个金额足够覆盖企业三年的合理利润。"
            "选择权在您手中，但犹豫的每一天都在增加¥{daily_late_fee}的额外成本。"
        ),
        "rebuttal_narrative": (
            "有人可能想'大不了注销公司重来'。但请注意：（1）金税四期将关联您的"
            "个人身份信息与所有历史企业记录，注销企业并不能消除历史数据痕迹；"
            "（2）偷税行为追征期最长为5年，且情节严重的可无限期追征；"
            "（3）法人代表被列入税收违法'黑名单'后，五年内不得担任任何公司的"
            "法定代表人。注销不是逃逸路径，而是自毁长城。"
        ),
        "timeline_pressure": (
            "滞纳金从税款滞纳之日起逐日累计，每一天都在增加您的损失敞口。"
            "若逾期超过180天仍未处理，税务机关将依法采取税收保全措施，"
            "包括冻结银行账户、查封财产等强制手段。"
        ),
    },
    "trudge": {
        "sop_title": "轻资产企业财税合规整改标准作业程序（SOP）",
        "micro_tasks": [
            {
                "task_id": 1,
                "task_name": "成本费用凭证自查",
                "action": "逐笔审核近36个月成本费用凭证，重点筛查咨询费/服务费/劳务费发票的真实性和关联性，标记无真实业务背景的异常凭证",
                "deadline": "7个工作日",
                "evidence_required": "每笔费用对应的合同、付款凭证、服务成果交付证明",
            },
            {
                "task_id": 2,
                "task_name": "股东借款清理",
                "action": "梳理'其他应收款'科目下股东及关联方借款明细，对超365天未归还的借款视同分红处理，完成个人所得税代扣代缴申报",
                "deadline": "15个工作日",
                "evidence_required": "借款合同、还款凭证或分红决议、完税证明",
            },
            {
                "task_id": 3,
                "task_name": "发票流-资金流比对",
                "action": "以合同台账为基准，逐月比对发票流与银行流水，识别开票金额与收款金额偏离超过30%的异常交易",
                "deadline": "10个工作日",
                "evidence_required": "比对表、差异说明、补充协议或更正后的发票",
            },
            {
                "task_id": 4,
                "task_name": "增值税进项合规核验",
                "action": "针对轻资产行业特点，核查无票采购比例及替代性进项凭证（如收购发票、海关缴款书）的合规性",
                "deadline": "10个工作日",
                "evidence_required": "采购合同、入库单、付款凭证、收购发票台账",
            },
            {
                "task_id": 5,
                "task_name": "建立税务内控台账",
                "action": "按国税发[2009]90号要求，设置税务风险管理岗位，建立月度税负率监控、季度发票异常预警、年度合规自查的制度化流程",
                "deadline": "30个工作日",
                "evidence_required": "内控制度文件、岗位职责说明、监控台账模板",
            },
        ],
        "compliance_framework": (
            "依据国税发[2009]90号《大企业税务风险管理指引（试行）》第3章"
            "'税务风险管理组织'和第4章'税务风险识别和评估'的要求，结合"
            "《税收征收管理法》第32条、第63条的相关规定，针对贵司作为轻资产"
            "企业暴露的成本费用率畸高、四流不一致、股东借款未清理等内控缺陷，"
            "制定以上五步整改SOP"
        ),
        "trust_building_closing": (
            "合规不是负担，而是企业长期健康发展的护城河。完成上述整改后，"
            "贵司的纳税信用等级将得到修复，这不仅意味着更低频次的税务检查，"
            "更意味着在融资授信、政府采购、资质审批中获得实实在在的竞争优势。"
            "我们随时愿意以专业、克制的态度提供进一步的技术指导。"
        ),
    },
    "metadata": {
        "model": "mock",
        "generated_at": "",
        "tokens_used": 0,
        "latency_seconds": 0.0,
    },
}


# ═══════════════════════════════════════════════════════
# 服务类
# ═══════════════════════════════════════════════════════

class LLMInterventionService:
    """
    NBT 三层行为干预大模型服务。

    单例模式，调用 generate_nbt_intervention() 生成结构化干预内容。
    """

    def __init__(self) -> None:
        self._provider = settings.llm_provider
        self._api_key = (
            settings.deepseek_api_key
            if self._provider == "deepseek"
            else settings.qwen_api_key
        )
        self._endpoint = LLM_ENDPOINTS.get(self._provider, LLM_ENDPOINTS["deepseek"])
        self._model_name = MODEL_NAMES.get(self._provider, "deepseek-chat")

    # ── 辅助方法 ────────────────────────────────────────

    @staticmethod
    def _serialize_risk_data(risk_data: dict[str, Any]) -> str:
        """将风险数据 dict 序列化为 JSON 字符串，Decimal 安全转换"""

        def _convert(obj: Any) -> Any:
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(i) for i in obj]
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        safe = _convert(risk_data)
        return json.dumps(safe, ensure_ascii=False, indent=2)

    def _build_system_prompt(self, risk_data_json: str) -> str:
        """构建 NBT 系统 Prompt"""
        return NBT_SYSTEM_PROMPT_TEMPLATE.format(risk_data_json=risk_data_json)

    def _build_user_prompt(self) -> str:
        """构建用户 Prompt（可补充额外引导）"""
        return (
            "请严格按照三层 NBT 结构输出干预内容。"
            "仅输出纯 JSON 对象，不要包含任何 Markdown 代码块标记、"
            "不要添加前缀或后缀文字、不要使用 ```json``` 包裹。"
            "确保所有金额数字与输入数据完全一致，不得修改。"
        )

    @staticmethod
    def _clean_json_response(raw_text: str) -> str:
        """
        清洗 LLM 返回的原始文本，提取纯 JSON。

        处理常见问题：
          - 首尾空白
          - ```json ... ``` 代码块包裹
          - ``` ... ``` 代码块包裹
          - 前置/后置文字说明
        """
        text = raw_text.strip()

        # 尝试去掉 ```json ... ``` 包裹
        if text.startswith("```"):
            # 找到第一个换行后的 {
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace != -1:
                text = text[first_brace : last_brace + 1]

        # 如果整个字符串不是以 { 开头，截取第一个 { 到最后一个 }
        if not text.startswith("{"):
            first_brace = text.find("{")
            if first_brace != -1:
                text = text[first_brace:]

        if not text.endswith("}"):
            last_brace = text.rfind("}")
            if last_brace != -1:
                text = text[: last_brace + 1]

        return text.strip()

    # ── 核心：LLM 异步调用 + 超时 + 重试 ────────────────

    async def _call_llm_api(
        self, messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        """
        异步调用大模型 API（DeepSeek / Qwen OpenAI 兼容模式）。

        Args:
            messages: [{"role": "system"|"user", "content": "..."}]

        Returns:
            API 原始响应 JSON

        Raises:
            TimeoutError: 超时且重试耗尽
            RuntimeError: API 返回非 200 状态码
            Exception: 网络/序列化等异常
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE,
            "response_format": {"type": "json_object"},  # 强制 JSON 输出
        }

        last_error: str = ""

        for attempt in range(1, LLM_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SEC) as client:
                    logger.info(
                        "LLM 调用 [%s/%s] provider=%s model=%s",
                        attempt, LLM_MAX_RETRIES,
                        self._provider, self._model_name,
                    )
                    t_start = time.monotonic()

                    response = await client.post(
                        self._endpoint,
                        headers=headers,
                        json=payload,
                    )
                    elapsed = time.monotonic() - t_start

                    if response.status_code == 200:
                        result = response.json()
                        logger.info(
                            "LLM 调用成功 [attempt=%s] latency=%.2fs",
                            attempt, elapsed,
                        )
                        return result

                    # 非 200 响应
                    error_body = response.text[:500]
                    logger.warning(
                        "LLM API 错误 [attempt=%s] status=%s body=%s",
                        attempt, response.status_code, error_body,
                    )
                    last_error = f"HTTP {response.status_code}: {error_body}"

                    if response.status_code in (429, 500, 502, 503):
                        # 可重试的状态码
                        if attempt < LLM_MAX_RETRIES:
                            delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                            logger.info("等待 %.1fs 后重试...", delay)
                            await asyncio.sleep(delay)
                            continue
                    elif response.status_code in (401, 403):
                        raise RuntimeError(
                            f"LLM API 认证失败，请检查 API Key 配置: {error_body}"
                        )
                    else:
                        if attempt < LLM_MAX_RETRIES:
                            delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                            await asyncio.sleep(delay)
                            continue

            except httpx.TimeoutException:
                last_error = f"请求超时 ({LLM_TIMEOUT_SEC}s)"
                logger.warning(
                    "LLM 请求超时 [attempt=%s/%s]", attempt, LLM_MAX_RETRIES,
                )
                if attempt < LLM_MAX_RETRIES:
                    delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                    continue

            except httpx.NetworkError as e:
                last_error = f"网络错误: {e}"
                logger.warning("LLM 网络错误 [attempt=%s]: %s", attempt, e)
                if attempt < LLM_MAX_RETRIES:
                    delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                    continue

            except Exception as e:
                last_error = f"未预期错误: {e}"
                logger.exception("LLM 未预期异常 [attempt=%s]", attempt)
                if attempt < LLM_MAX_RETRIES:
                    delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                    continue

        raise TimeoutError(
            f"LLM 调用失败，已重试 {LLM_MAX_RETRIES} 次: {last_error}"
        )

    async def _call_real_llm(
        self, risk_data_json: str
    ) -> NBTInterventionResponse:
        """
        真实 LLM 调用 → Pydantic 解析 → 返回结构化结果
        """
        messages = [
            {"role": "system", "content": self._build_system_prompt(risk_data_json)},
            {"role": "user", "content": self._build_user_prompt()},
        ]

        t0 = time.monotonic()
        api_response = await self._call_llm_api(messages)
        latency = time.monotonic() - t0

        # ── 从 API 响应中提取 LLM 文本 ──
        try:
            choices = api_response.get("choices", [])
            if not choices:
                raise ValueError("LLM 返回空 choices 列表")
            llm_text = choices[0].get("message", {}).get("content", "")
            if not llm_text:
                raise ValueError("LLM 返回空 content")
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"无法解析 LLM 响应结构: {e}") from e

        # ── 清洗 JSON ──
        cleaned_json = self._clean_json_response(llm_text)
        logger.debug("LLM 清洗后 JSON 前200字符: %s", cleaned_json[:200])

        # ── Pydantic 严格验证 ──
        try:
            parsed = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            logger.error("LLM 返回非合法 JSON: %s", cleaned_json[:500])
            raise ValueError(
                f"LLM 返回的文本不是有效的 JSON: {e}"
            ) from e

        try:
            nbt_response = NBTInterventionResponse.model_validate(parsed)
        except ValidationError as e:
            logger.error(
                "NBT 响应 Pydantic 校验失败: %s\n原始 JSON: %s",
                e.errors(),
                cleaned_json[:1000],
            )
            raise ValueError(
                f"LLM 返回的 JSON 不符合 NBT 三层结构规范: {e.errors()}"
            ) from e

        # ── 补充元数据 ──
        usage = api_response.get("usage", {})
        nbt_response.metadata = {
            "model": self._model_name,
            "provider": self._provider,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tokens_used": usage.get("total_tokens", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "latency_seconds": round(latency, 3),
        }

        return nbt_response

    # ── 主入口 ──────────────────────────────────────────

    async def generate_nbt_intervention(
        self,
        risk_data: dict[str, Any],
    ) -> NBTInterventionResponse:
        """
        生成 NBT 三层行为干预内容。

        调用 DeepSeek/Qwen 大模型，对传入的风险数据进行三层行为干预
        （Nudge-Budge-Trudge）分析，返回严格 Pydantic 验证的结构化结果。

        Args:
            risk_data: 风险数据载荷字典，应包含：
              - 轻资产/重资产属性标识
              - 成本费用率畸高预警
              - 涉嫌虚增费用记录
              - 个税穿透补缴金额
              - 罚款倍数与本金
              - 滞纳金日累计/年化数据

        Returns:
            NBTInterventionResponse: 三层结构化的 NBT 行为干预内容

        Raises:
            ValueError: 输入数据无效或 LLM 返回不合规
            TimeoutError: LLM 调用超时（已重试3次）
            RuntimeError: LLM API Key 无效
        """
        # ── 输入校验 ──
        if not risk_data or not isinstance(risk_data, dict):
            raise ValueError("risk_data 必须是非空 dict")

        logger.info("开始生成 NBT 干预内容...")

        # ── 序列化风险数据 ──
        risk_data_json = self._serialize_risk_data(risk_data)
        logger.debug("风险数据 JSON 长度: %d 字符", len(risk_data_json))

        # ── 判断是真实调用还是 Mock ──
        if not self._api_key:
            logger.warning("未配置 LLM API Key，使用 Mock 降级输出")
            return self._generate_mock_fallback(risk_data)

        try:
            return await self._call_real_llm(risk_data_json)
        except TimeoutError:
            logger.error("LLM 调用超时，降级到 Mock 输出")
            return self._generate_mock_fallback(risk_data)
        except (RuntimeError, ValueError) as e:
            logger.error("LLM 调用失败(%s)，降级到 Mock 输出", type(e).__name__)
            return self._generate_mock_fallback(risk_data)
        except Exception as e:
            logger.exception("LLM 调用未预期异常，降级到 Mock 输出")
            return self._generate_mock_fallback(risk_data)

    # ── Mock 降级 ───────────────────────────────────────

    def _generate_mock_fallback(
        self, risk_data: dict[str, Any]
    ) -> NBTInterventionResponse:
        """
        当 LLM 不可用时，使用内置模板生成 Mock 三层干预内容。

        原型阶段保障前端联调可用，产品化阶段移除。
        """
        # 提取关键数值用于模板插值
        compound = risk_data.get("compound_penalty", {})
        penalty = risk_data.get("penalty", {})
        total_exposure = compound.get("total_exposure", "0")
        principal = penalty.get("total_unpaid_principal", compound.get("total_unpaid_principal", "0"))

        # 计算日滞纳金
        try:
            _daily = Decimal(str(principal or "0")) * Decimal("0.0005")
            daily_late_fee = f"{_daily:,.2f}"
        except Exception:
            daily_late_fee = "待计算"

        # 计算差额
        try:
            gap = Decimal(str(total_exposure or "0")) - Decimal(str(principal or "0"))
            gap_str = f"{gap:,.2f}"
        except Exception:
            gap_str = "待计算"

        mock_copy = json.loads(json.dumps(_MOCK_NBT_RESPONSE, ensure_ascii=False))

        # 模板插值
        loss = mock_copy["budge"]["loss_comparison"]
        loss = loss.replace("{total_exposure}", str(total_exposure))
        loss = loss.replace("{principal}", str(principal))
        loss = loss.replace("{gap}", gap_str)
        loss = loss.replace("{daily_late_fee}", daily_late_fee)
        mock_copy["budge"]["loss_comparison"] = loss

        mock_copy["metadata"] = {
            "model": "mock-fallback",
            "provider": self._provider,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tokens_used": 0,
            "latency_seconds": 0.0,
            "fallback_reason": "LLM unavailable",
        }

        return NBTInterventionResponse.model_validate(mock_copy)


# ── 模块单例 ──
llm_intervention_service = LLMInterventionService()
