"""
NBT 行为干预大模型响应 Schema

定义「Nudge-Budge-Trudge」三层结构化输出的严格 Pydantic 验证模型。
"""
from pydantic import BaseModel, Field


# ── 三层子模型 ──

class NudgeLayer(BaseModel):
    """
    环境助推层：利用色彩心理学与数据直击行业痛点，引起直觉警觉。

    关键要素：
      - 稽查概率达 94% 的无感陈述
      - 轻资产缺合法进项导致利润虚高的行业痛点
      - 打破"认知污泥"（cognitive sludge）
    """
    risk_statement: str = Field(
        ...,
        min_length=50,
        description="直击痛点的风险陈述，包含稽查概率数据和行业痛点分析",
    )
    psychological_trigger: str = Field(
        ...,
        min_length=30,
        description="针对「控制错觉」与「盲目乐观」偏差的心理触发语",
    )
    visual_recommendation: str = Field(
        ...,
        min_length=20,
        description="建议的视觉呈现方式（红/橙/黄配色方案）",
    )


class BridgeLayer(BaseModel):
    """
    信念重塑层：深度应用前景理论的损失框架（Loss Framing）。

    操作核心：
      - 未来三年复合稽查预期损失 vs 当期零罚款整改成本 的戏剧化并列对比
      - 彻底粉碎"大不了注销破产"的逃避心理
      - 使用精确的金额数字（不得修改任何数值）
    """
    loss_comparison: str = Field(
        ...,
        min_length=100,
        description=(
            "损失框架对比叙述：未来三年叠加行政处罚与单利复现滞纳金的"
            "复合稽查预期损失总额，与当期立刻合规自查的'零罚款'整改成本"
            "进行强烈、戏剧化的并列对比"
        ),
    )
    rebuttal_narrative: str = Field(
        ...,
        min_length=50,
        description="针对性破除'大不了注销破产'逃避心理的论据",
    )
    timeline_pressure: str = Field(
        ...,
        min_length=30,
        description="时间紧迫感塑造（滞纳金日累计的不可逆性）",
    )


class TrudgeLayer(BaseModel):
    """
    长效信任建设层：生成轻量化整改 SOP（标准作业程序）。

    依据：
      - 国税发[2009]90号《大企业税务风险管理指引（试行）》
      - 针对暴露的内控缺陷，逐条生成可打卡的微任务
    """
    sop_title: str = Field(
        ...,
        min_length=10,
        description="整改SOP标题",
    )
    micro_tasks: list[dict] = Field(
        ...,
        min_length=1,
        max_length=10,
        description=(
            "轻量化整改微任务列表。每项包含：\n"
            "  - task_id: 任务序号（1-n）\n"
            "  - task_name: 任务名称（≤20字）\n"
            "  - action: 具体操作步骤（≤100字）\n"
            "  - deadline: 建议完成时限（如'7个工作日'）\n"
            "  - evidence_required: 需留存的证据材料"
        ),
    )
    compliance_framework: str = Field(
        ...,
        min_length=50,
        description="引用的内控框架标准（国税发[2009]90号对应条款）",
    )
    trust_building_closing: str = Field(
        ...,
        min_length=30,
        description="信任建设收尾语：税务机关作为合规伙伴的定位重塑",
    )


# ── 顶层响应模型 ──

class NPTMixSchema(BaseModel):
    """NPT 动态配比信息"""
    npt_mix: dict[str, float] = Field(
        ..., description="NPT 三级干预配比 {nudge, budge, trudge}"
    )
    quadrant: str = Field(..., description="象限标识 Q1/Q2/Q3/Q4")
    quadrant_name: str = Field(..., description="象限中文名称")
    scheme_id: str = Field(..., description="配比方案ID")
    scheme_description: str = Field(..., description="配比方案说明")
    primary_strategy: str = Field(..., description="主导策略")
    intensity: str = Field(..., description="干预强度")


class NBTInterventionResponse(BaseModel):
    """
    NBT 三层行为干预的完整 LLM 响应。

    三层结构：
      1. nudge（环境助推）：触发直觉警觉
      2. budge（信念重塑）：损失框架对比
      3. trudge（长效信任建设）：整改SOP微任务
    """
    nudge: NudgeLayer = Field(..., description="第一层：环境助推")
    budge: BridgeLayer = Field(..., description="第二层：信念重塑")
    trudge: TrudgeLayer = Field(..., description="第三层：长效信任建设")

    metadata: dict = Field(
        default_factory=dict,
        description="元数据：模型名称、token 用量、延迟等",
    )

    # ── P1: NPT 动态配比 ──
    dynamic_mix: NPTMixSchema | None = Field(
        default=None,
        description="NPT 动态配比结果（自动基于合规数据判定）",
    )
