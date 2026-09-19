"""风险引擎参数配置服务（B1 参数配置化）

PDCA 闭环的配置底座：W（权重）/ S（严重度倍数）/ P（概率）/ C（内控）/
R（修复加分）/ Q（法定信用扣分）等全部评分参数统一收口到 risk_config 表，
引擎从配置读取，未配置项回退到代码内权威默认值。

设计约束：
  - get_risk_config 是「确定性」读取：DB 覆盖默认值，表缺失/读失败回退默认，永不抛错；
  - 所有默认值附带权威来源（source），与《风险评分与风险等级优化建议说明书》§九多源互证表一致；
  - 配置变更（upsert）自动失效 risk_scan_cache，避免陈旧评分滞留。
"""
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_config import RiskConfig
from app.core.cache import risk_scan_cache

_logger = logging.getLogger(__name__)

# ── 权威默认参数（未配置时的兜底；source 见 说明书 §九）────────────────────────

DEFAULT_RISK_CONFIG: dict[str, dict[str, Any]] = {
    # ── 风险等级阈值（评分语义：分数越高风险越高）──
    "risk_high_threshold": {
        "value": 70.0, "type": "float",
        "description": "7 维综合风险分 ≥ 70 判为高风险（旧引擎）",
        "source": "系统既有基线；对齐金税四期多维度分级实践",
    },
    "risk_medium_threshold": {
        "value": 40.0, "type": "float",
        "description": "7 维综合风险分 ≥ 40 判为中风险（旧引擎）",
        "source": "系统既有基线",
    },
    "risk_critical_threshold": {
        "value": 80.0, "type": "float",
        "description": "5 维综合风险分 ≥ 80 判为 critical",
        "source": "系统既有基线（5 级映射）",
    },
    "risk_high_level_threshold": {
        "value": 60.0, "type": "float",
        "description": "5 维综合风险分 ≥ 60 判为 high",
        "source": "系统既有基线",
    },
    "risk_medium_high_threshold": {
        "value": 45.0, "type": "float",
        "description": "5 维综合风险分 ≥ 45 判为 medium_high",
        "source": "系统既有基线",
    },
    "risk_medium_level_threshold": {
        "value": 30.0, "type": "float",
        "description": "5 维综合风险分 ≥ 30 判为 medium",
        "source": "系统既有基线",
    },
    "high_dimension_score_threshold": {
        "value": 70.0, "type": "float",
        "description": "单维度风险分 ≥ 该值计为「高危维度」（一票否决计数用）",
        "source": "系统既有基线",
    },

    # ── 权重 W（7 维旧引擎 / 5 维新引擎）──
    "weights_7dim": {
        "value": {
            "four_flow_match": 0.30,
            "private_card_ratio": 0.20,
            "large_personal_transfer": 0.05,
            "cost_deviation": 0.15,
            "tax_burden_deviation": 0.15,
            "invoice_bank_mismatch": 0.05,
            "input_output_imbalance": 0.10,
        },
        "type": "json",
        "description": "7 维旧引擎各维度权重（合计 1.0）",
        "source": "系统既有基线；四流匹配为金税四期核心稽查对象（国税发〔1995〕192 号）权重最高",
    },
    "weights_5dim": {
        "value": {
            "macro_internal_control": 0.20,
            "vat_gaar": 0.25,
            "iit_hidden_dividend": 0.15,
            "compound_penalty": 0.15,
            "four_flow_match": 0.25,
        },
        "type": "json",
        "description": "5 维新引擎各维度权重（合计 1.0）",
        "source": "系统既有基线",
    },

    # ── S：罚款/严重度倍数（征管法第 63/64 条：0.5-5 倍；发票管理办法第 37 条：虚开 1-5 倍）──
    "penalty_multiplier": {
        "value": {
            "low": 0.5,
            "medium": 1.5,
            "medium_high": 2.5,
            "high": 3.5,
            "critical": 5.0,
        },
        "type": "json",
        "description": "偷税/不申报行政罚款倍数（按风险等级阶梯，对应征管法 0.5-5 倍）",
        "source": "《中华人民共和国税收征收管理法》第六十三条/第六十四条（处不缴或少缴税款 50% 以上 5 倍以下罚款）",
    },
    "ghost_invoice_multiplier": {
        "value": 2.0, "type": "float",
        "description": "虚开发票叠加罚款倍数",
        "source": "《中华人民共和国发票管理办法》第三十七条（虚开金额 1 倍以上 5 倍以下罚款；保守档取 2 倍）",
    },
    "late_fee_daily_rate": {
        "value": 0.0005, "type": "float",
        "description": "滞纳金日利率",
        "source": "《中华人民共和国税收征收管理法》第三十二条（按日加收滞纳税款万分之五的滞纳金）",
    },
    "iit_dividend_rate": {
        "value": 0.20, "type": "float",
        "description": "股息红利所得个人所得税税率（股东借款视同分红穿透）",
        "source": "《中华人民共和国个人所得税法》第三条/财税〔2003〕158 号第二条（利息、股息、红利所得 20%）",
    },

    # ── R：修复加分（整改完成率联动，R ≤ D 约束）──
    "reduction_pct_per_task": {
        "value": 0.15, "type": "float",
        "description": "[已废弃] V4 §3.2 方案 B 起整改率改为权重比口径（已验证权重÷可整改权重，见 compliance_adjustment.PRIORITY_WEIGHTS），本键不再被引擎读取，仅为历史兼容保留",
        "source": "系统既有合规调整规则（compute_compliance_adjusted_risk）",
    },
    "reduction_pct_max": {
        "value": 0.80, "type": "float",
        "description": "[已废弃] V4 §3.2 方案 B 起整改率为比值口径（天然 ≤100%），80% 上限已废除（Q4），本键不再被引擎读取，仅为历史兼容保留",
        "source": "系统既有合规调整规则；说明书修正公式缺陷 4（R = D × min(0.80, 0.15×completed)）",
    },

    # ── Q：法定信用扣分（纳税信用评价指标，2025 年第 12 号起评 100/93/90）──
    "credit_deduction_items": {
        "value": [
            {
                "item": "未按规定期限申报",
                "deduction": 5.0,
                "basis": "《纳税信用评价指标和评价方式（试行）》（国家税务总局公告 2014 年第 48 号）：未按规定期限申报，扣 5 分/次",
            },
            {
                "item": "未按规定期限缴纳税款",
                "deduction": 5.0,
                "basis": "同上：未按规定期限缴纳税款，扣 5 分/次",
            },
            {
                "item": "未按规定报送财务报表等涉税资料",
                "deduction": 3.0,
                "basis": "同上：未按规定报送财务会计制度或财务、会计处理办法，扣 3 分/次",
            },
            {
                "item": "偷税、虚开发票等严重失信行为",
                "deduction": 11.0,
                "basis": "同上：直接判为 D 级的情形由《纳税缴费信用管理办法》（2025 年第 12 号）与一票否决兜底，此处保留扣分项用于非直接判级情节",
            },
        ],
        "type": "json",
        "description": "法定信用固定扣分项（不随企业内控水平打折，对应公式 ΣQ_j）",
        "source": "《纳税信用评价指标和评价方式（试行）》（国家税务总局公告 2014 年第 48 号）；《纳税缴费信用管理办法》（国家税务总局公告 2025 年第 12 号）",
    },
}


def _default_value(key: str) -> Any:
    """取默认配置值（未知键返回 None）。"""
    meta = DEFAULT_RISK_CONFIG.get(key)
    return meta["value"] if meta else None


async def get_risk_config(db: AsyncSession) -> dict[str, Any]:
    """读取全部生效配置：数据库覆盖默认值。

    表缺失或读取失败时回退默认配置并记录日志（保证引擎永不因配置中断）。
    """
    config = {key: meta["value"] for key, meta in DEFAULT_RISK_CONFIG.items()}
    try:
        result = await db.execute(select(RiskConfig))
        for row in result.scalars().all():
            if row.config_key in config:
                config[row.config_key] = row.config_value
    except Exception:
        _logger.exception("读取 risk_config 失败，回退代码内权威默认值")
    return config


async def upsert_risk_config(
    db: AsyncSession,
    updates: dict[str, Any],
    updated_by: str | None = None,
) -> dict[str, Any]:
    """批量更新配置（仅接受 DEFAULT_RISK_CONFIG 已定义键），提交后失效扫描缓存。

    Returns:
        实际写入的 {key: value} 映射（未知键被忽略）。
    """
    applied: dict[str, Any] = {}
    for key, value in updates.items():
        meta = DEFAULT_RISK_CONFIG.get(key)
        if meta is None:
            _logger.warning("忽略未知配置键: %s", key)
            continue
        result = await db.execute(
            select(RiskConfig).where(RiskConfig.config_key == key)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            row.config_value = value
            row.updated_by = updated_by
        else:
            db.add(RiskConfig(
                config_key=key,
                config_value=value,
                config_type=meta["type"],
                description=meta["description"],
                source=meta["source"],
                updated_by=updated_by,
            ))
        applied[key] = value
    await db.commit()
    # 配置变更 → 全部扫描结果失效，强制下次扫描按新参数重算
    await risk_scan_cache.invalidate()
    return applied


# 便捷取值：引擎侧只关心数值，避免逐处判 None
def cfg_float(config: dict[str, Any], key: str, default: float) -> float:
    value = config.get(key)
    return float(value) if isinstance(value, (int, float)) else default


def cfg_json(config: dict[str, Any], key: str, default: Any) -> Any:
    return config.get(key) if config.get(key) is not None else default
