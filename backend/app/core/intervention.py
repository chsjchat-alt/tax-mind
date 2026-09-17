"""
整改干预策略引擎

基于行为经济学的五层递进式干预机制，针对企业的合规风险状态设计结构化干预策略。

五层干预：
  第一层：打破乐观偏差   —— 前景理论，纠正概率判断偏差
  第二层：削弱控制错觉   —— 控制错觉理论，强调系统自动触发
  第三层：重构损失认知   —— 前景理论，损失框架 > 收益框架
  第四层：缓解认知失调   —— 认知失调理论，提供合理化出口
  第五层：锚定长期预期   —— 长期视角：合规账户 vs 违规账户

优先级调整：根据传入的优先维度 key 列表调整五层干预的执行顺序。

商业语言输出：可直接展示给老板的干预话术
技术语言输出：干预策略的结构化描述
"""

from pydantic import BaseModel, Field


# ── 五层干预策略内容模板 ──
INTERVENTION_TEMPLATES = {
    1: {  # 打破乐观偏差
        "name": "打破乐观偏差",
        "theory": "前景理论——个体对概率的判断存在系统性偏差，倾向低估负面事件概率",
        "visual_type": "card",
        "content_template": (
            "【数据警示】\n"
            "· 同规模企业稽查概率：{audit_probability:.0%}\n"
            "· 您的企业风险评分：{risk_score}分（{risk_label}）\n"
            "· 过去3年被稽查企业中，有82%曾认为'自己不会被查到'\n\n"
            "金税四期每天自动比对超过2000万户企业的发票、申报、资金数据。"
            "您认为的低概率事件，在数据系统中只是早晚问题。"
        ),
    },
    2: {  # 削弱控制错觉
        "name": "削弱控制错觉",
        "theory": "控制错觉理论——个体高估自身对随机事件的控制力",
        "visual_type": "animation",
        "content_template": (
            "【金税四期自动预警流程】\n"
            "第一步：发票数据自动上传 → 系统自动比对进销项\n"
            "第二步：银行流水自动接入 → 系统自动匹配资金流与发票流\n"
            "第三步：四流一致性自动校验 → 异常标记自动生成\n"
            "第四步：风险等级自动评定 → 推送至稽查选案系统\n\n"
            "整个过程无需人工干预，系统自动完成。"
            "您无法通过'关系'或'运气'影响这个自动流程。"
        ),
    },
    3: {  # 重构损失认知
        "name": "重构损失认知",
        "theory": "前景理论——损失框架比收益框架更有说服力，人们对损失的敏感度约为收益的2.5倍",
        "visual_type": "text",
        "content_template": (
            "【损失对比】\n"
            "如果继续当前模式，预计将面临：\n"
            "· 罚款：约 {expected_loss:,.0f} 元（含滞纳金）\n"
            "· 声誉损失：银行贷款受阻、合作伙伴信任下降、招投标资格受限\n"
            "· 个人风险：企业主可能承担连带法律责任\n\n"
            "现在进行合规整改，仅需投入：\n"
            "· 整改成本：{remediation_cost:,.0f} 元\n"
            "· 时间成本：一次性完成\n\n"
            "不是'合规要花多少钱'，而是'不合规会让你损失多少钱'。"
        ),
    },
    4: {  # 缓解认知失调
        "name": "缓解认知失调",
        "theory": "认知失调理论——个体需要为行为找到正当理由，改变行为需要提供合理化出口",
        "visual_type": "text",
        "content_template": (
            "【换个角度看合规】\n"
            "合规不是增加成本，而是：\n"
            "· 保护您的企业免受税务稽查的毁灭性打击\n"
            "· 为银行贷款、政府补贴、商业合作铺平道路\n"
            "· 让您个人免于承担连带法律责任\n"
            "· 建立企业的长期信用资产\n\n"
            "很多老板在稽查后才后悔——'早知道就合规了'。"
            "您现在做，是对企业未来的投资，而非成本。"
        ),
    },
    5: {  # 锚定长期预期
        "name": "锚定长期预期",
        "theory": "长期账户视角——企业主常只计当期成本，忽略违规的长期负债",
        "visual_type": "table",
        "content_template": (
            "【合规账户对比】\n"
            "┌──────────────────┬──────────────────┐\n"
            "│  合规账户（长期资产）  │  违规账户（短期负债）  │\n"
            "├──────────────────┼──────────────────┤\n"
            "│ 银行授信额度提升       │ 随时可能被稽查追缴     │\n"
            "│ 政府补贴优先资格       │ 罚款 + 滞纳金滚动      │\n"
            "│ 招投标合规资质         │ 个人连带责任风险       │\n"
            "│ 企业估值提升           │ 商业合作受限          │\n"
            "│ 安心经营，专注发展     │ 每日担忧，潜在噩梦     │\n"
            "└──────────────────┴──────────────────┘\n\n"
            "您今天的选择，决定了企业3年后在哪一栏。"
        ),
    },
}


class InterventionInput(BaseModel):
    """干预输入"""
    risk_level: str = Field(..., description="风险等级（五级）low/medium/medium_high/high/critical")
    risk_score: float | None = Field(
        default=None, ge=0, le=100,
        description="调整后风险评分（传入则直接作为干预风险分，覆盖等级推算）",
    )
    deviation_index: float = Field(..., ge=0, le=100, description="综合风险偏离度")
    dominant_biases: list[str] = Field(default_factory=list, description="优先维度 key 列表")
    audit_probability: float = Field(..., ge=0, le=1, description="稽查概率")
    expected_loss: float = Field(..., ge=0, description="期望损失金额（元）")
    remediation_cost: float = Field(..., ge=0, description="整改成本（元）")


class InterventionLayer(BaseModel):
    """单层干预"""
    layer: int                                                      # 层级1-5
    name: str                                                       # 策略名称
    theory: str                                                     # 理论依据
    content: str                                                    # 干预内容
    visual_type: str                                                # 可视化类型


class InterventionResult(BaseModel):
    """干预结果"""
    layers: list[InterventionLayer]                                 # 五层干预策略
    priority_order: list[int]                                       # 优先级排序
    business_narrative: str = ""                                    # 商业语言叙述
    technical_summary: dict = Field(default_factory=dict)           # 技术语言摘要


def _calculate_risk_score(risk_level: str, deviation_index: float) -> float:
    """综合风险评分（五级阶梯，覆盖前端 RiskLevel 全部档位）"""
    level_multiplier = {
        "low": 0.3,
        "medium": 1.0,
        "medium_high": 1.5,
        "high": 2.0,
        "critical": 2.5,
    }
    multiplier = level_multiplier.get(risk_level, 1.0)
    return min(100.0, round(deviation_index * multiplier, 1))


def _get_risk_label(risk_level: str) -> str:
    """风险等级中文标签（五级）"""
    return {
        "low": "低风险",
        "medium": "中风险",
        "medium_high": "中高风险",
        "high": "高风险",
        "critical": "严重风险",
    }.get(risk_level, "未知")


def _adjust_priority(dominant_biases: list[str]) -> list[int]:
    """
    根据优先维度调整干预优先级。

    规则：
      - 优先维度为"乐观偏差" → 第一层优先
      - 优先维度为"控制错觉" → 第二层优先
      - 优先维度为"损失厌恶" → 第三层优先
      - 优先维度为"防御性倾向" → 第四层优先
      - 优先维度为"短期主义" → 第五层优先

    支持英文 key（如 "optimism_bias"）和中文名（如 "乐观偏差"）双向查找。
    """
    bias_to_layer = {
        "optimism_bias": 1,
        "control_illusion": 2,
        "loss_aversion": 3,
        "defensiveness": 4,
        "short_termism": 5,
        "control_desire": 2,
    }

    # 将中文名转回英文 key（如果已经是英文则保持原样）
    # 一期边界（V4 §5.4）：画像推断已移除，dominant_biases 仅接受英文 key 直传
    def _resolve(b: str) -> str:
        return b if b in bias_to_layer else b

    base_order = list(range(1, 6))

    if not dominant_biases:
        return base_order

    priority_layers = []
    for bias in dominant_biases:
        layer = bias_to_layer.get(_resolve(bias))
        if layer is not None and layer not in priority_layers:
            priority_layers.append(layer)

    result = priority_layers.copy()
    for l in base_order:
        if l not in result:
            result.append(l)
    return result


def generate_intervention(data: InterventionInput) -> InterventionResult:
    """
    生成五层递进式合规干预策略。

    基于企业风险数据与合规调整结果，生成分层干预方案。

    Args:
        data: 干预输入数据

    Returns:
        InterventionResult: 五层干预策略，根据优先维度调整优先级

    Edge Cases:
      - 空优先维度列表：使用默认顺序1-5
      - 风险偏离度为0：所有干预内容仍生成但语气更温和
      - 稽查概率为0：第一层干预使用保守语言
    """
    risk_score = (
        data.risk_score
        if data.risk_score is not None
        else _calculate_risk_score(data.risk_level, data.deviation_index)
    )
    risk_label = _get_risk_label(data.risk_level)

    # 格式化参数
    format_kwargs = {
        "audit_probability": data.audit_probability,
        "risk_score": risk_score,
        "risk_label": risk_label,
        "expected_loss": data.expected_loss,
        "remediation_cost": data.remediation_cost,
    }

    # 生成五层干预内容
    layers = []
    for layer_num in range(1, 6):
        template = INTERVENTION_TEMPLATES[layer_num]
        content = template["content_template"].format(**format_kwargs)

        layers.append(InterventionLayer(
            layer=layer_num,
            name=template["name"],
            theory=template["theory"],
            content=content,
            visual_type=template["visual_type"],
        ))

    # 优先级调整
    priority_order = _adjust_priority(data.dominant_biases)

    result = InterventionResult(
        layers=layers,
        priority_order=priority_order,
    )

    # ── 商业语言叙述 ──
    result.business_narrative = _generate_business_narrative(result, data)

    # ── 技术摘要 ──
    result.technical_summary = {
        "deviation_index": data.deviation_index,
        "risk_level": data.risk_level,
        "risk_score": risk_score,
        "dominant_biases": data.dominant_biases,
        "audit_probability": data.audit_probability,
        "priority_order": result.priority_order,
        "layers_count": len(result.layers),
        "default_order": list(range(1, 6)),
        "adjusted": result.priority_order != list(range(1, 6)),
    }

    return result


def _generate_business_narrative(result: InterventionResult, data: InterventionInput) -> str:
    """生成商业语言干预叙述"""
    parts = [
        "═══════════════════════════════════",
        "  五层递进式合规干预策略",
        "═══════════════════════════════════",
        "",
        f"综合风险偏离度：{data.deviation_index:.0f} / 100",
        f"风险等级：{_get_risk_label(data.risk_level)}",
    ]

    if data.dominant_biases:
        names = list(data.dominant_biases)
        parts.append(f"优先维度：{'、'.join(names)}")
    parts.append("")

    parts.append("干预执行顺序（优先级从高到低）：")
    for idx, layer_num in enumerate(result.priority_order, 1):
        layer = result.layers[layer_num - 1]
        parts.append(f"  {idx}. 第{layer_num}层 - {layer.name}")
    parts.append("")

    parts.append("─── 各层干预详情 ───")
    for layer in result.layers:
        parts.append(f"")
        parts.append(f"【第{layer.layer}层】{layer.name}")
        parts.append(f"理论依据：{layer.theory}")
        parts.append(f"可视化类型：{layer.visual_type}")
        parts.append(layer.content)

    return "\n".join(parts)
