"""create risk_config table

Revision ID: 008
Revises: 007
Create Date: 2026-08-14

B1 参数配置化：风险引擎全部评分参数（W/S/P/C/R/Q）收口到 risk_config 表，
种子数据内置权威默认值与来源标注（多源互证，见《风险评分与风险等级优化建议说明书》§九）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_CONFIG: list[dict] = [
    {
        "config_key": "risk_high_threshold",
        "config_value": 70.0, "config_type": "float",
        "description": "7 维综合风险分 ≥ 70 判为高风险（旧引擎）",
        "source": "系统既有基线；对齐金税四期多维度分级实践",
    },
    {
        "config_key": "risk_medium_threshold",
        "config_value": 40.0, "config_type": "float",
        "description": "7 维综合风险分 ≥ 40 判为中风险（旧引擎）",
        "source": "系统既有基线",
    },
    {
        "config_key": "risk_critical_threshold",
        "config_value": 80.0, "config_type": "float",
        "description": "5 维综合风险分 ≥ 80 判为 critical",
        "source": "系统既有基线（5 级映射）",
    },
    {
        "config_key": "risk_high_level_threshold",
        "config_value": 60.0, "config_type": "float",
        "description": "5 维综合风险分 ≥ 60 判为 high",
        "source": "系统既有基线",
    },
    {
        "config_key": "risk_medium_high_threshold",
        "config_value": 45.0, "config_type": "float",
        "description": "5 维综合风险分 ≥ 45 判为 medium_high",
        "source": "系统既有基线",
    },
    {
        "config_key": "risk_medium_level_threshold",
        "config_value": 30.0, "config_type": "float",
        "description": "5 维综合风险分 ≥ 30 判为 medium",
        "source": "系统既有基线",
    },
    {
        "config_key": "high_dimension_score_threshold",
        "config_value": 70.0, "config_type": "float",
        "description": "单维度风险分 ≥ 该值计为「高危维度」（一票否决计数用）",
        "source": "系统既有基线",
    },
    {
        "config_key": "weights_7dim",
        "config_value": {
            "four_flow_match": 0.30, "private_card_ratio": 0.20,
            "large_personal_transfer": 0.05, "cost_deviation": 0.15,
            "tax_burden_deviation": 0.15, "invoice_bank_mismatch": 0.05,
            "input_output_imbalance": 0.10,
        },
        "config_type": "json",
        "description": "7 维旧引擎各维度权重（合计 1.0）",
        "source": "系统既有基线；四流匹配为金税四期核心稽查对象（国税发〔1995〕192 号）权重最高",
    },
    {
        "config_key": "weights_5dim",
        "config_value": {
            "macro_internal_control": 0.20, "vat_gaar": 0.25,
            "iit_hidden_dividend": 0.15, "compound_penalty": 0.15,
            "four_flow_match": 0.25,
        },
        "config_type": "json",
        "description": "5 维新引擎各维度权重（合计 1.0）",
        "source": "系统既有基线",
    },
    {
        "config_key": "penalty_multiplier",
        "config_value": {
            "low": 0.5, "medium": 1.5, "medium_high": 2.5,
            "high": 3.5, "critical": 5.0,
        },
        "config_type": "json",
        "description": "偷税/不申报行政罚款倍数（按风险等级阶梯，对应征管法 0.5-5 倍）",
        "source": "《中华人民共和国税收征收管理法》第六十三条/第六十四条（处不缴或少缴税款 50% 以上 5 倍以下罚款）",
    },
    {
        "config_key": "ghost_invoice_multiplier",
        "config_value": 2.0, "config_type": "float",
        "description": "虚开发票叠加罚款倍数",
        "source": "《中华人民共和国发票管理办法》第三十七条（虚开金额 1 倍以上 5 倍以下罚款；保守档取 2 倍）",
    },
    {
        "config_key": "late_fee_daily_rate",
        "config_value": 0.0005, "config_type": "float",
        "description": "滞纳金日利率",
        "source": "《中华人民共和国税收征收管理法》第三十二条（按日加收滞纳税款万分之五的滞纳金）",
    },
    {
        "config_key": "iit_dividend_rate",
        "config_value": 0.20, "config_type": "float",
        "description": "股息红利所得个人所得税税率（股东借款视同分红穿透）",
        "source": "《中华人民共和国个人所得税法》第三条/财税〔2003〕158 号第二条（利息、股息、红利所得 20%）",
    },
    {
        "config_key": "reduction_pct_per_task",
        "config_value": 0.15, "config_type": "float",
        "description": "每个完成的整改任务降低风险比例",
        "source": "系统既有合规调整规则（compute_compliance_adjusted_risk）",
    },
    {
        "config_key": "reduction_pct_max",
        "config_value": 0.80, "config_type": "float",
        "description": "修复加分上限：最多降低 80% 风险（R ≤ D 约束）",
        "source": "系统既有合规调整规则；说明书修正公式缺陷 4",
    },
    {
        "config_key": "credit_deduction_items",
        "config_value": [
            {"item": "未按规定期限申报", "deduction": 5.0,
             "basis": "《纳税信用评价指标和评价方式（试行）》（国家税务总局公告 2014 年第 48 号）：未按规定期限申报，扣 5 分/次"},
            {"item": "未按规定期限缴纳税款", "deduction": 5.0,
             "basis": "同上：未按规定期限缴纳税款，扣 5 分/次"},
            {"item": "未按规定报送财务报表等涉税资料", "deduction": 3.0,
             "basis": "同上：未按规定报送财务会计制度或财务、会计处理办法，扣 3 分/次"},
            {"item": "偷税、虚开发票等严重失信行为", "deduction": 11.0,
             "basis": "同上：直接判 D 级情形由《纳税缴费信用管理办法》（2025 年第 12 号）与一票否决兜底"},
        ],
        "config_type": "json",
        "description": "法定信用固定扣分项（不随企业内控水平打折，对应公式 ΣQ_j）",
        "source": "《纳税信用评价指标和评价方式（试行）》（国家税务总局公告 2014 年第 48 号）；《纳税缴费信用管理办法》（国家税务总局公告 2025 年第 12 号）",
    },
]


def upgrade() -> None:
    op.create_table(
        "risk_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("config_key", sa.String(100), nullable=False),
        sa.Column("config_value", SQLiteJSON(), nullable=False),
        sa.Column("config_type", sa.String(20), nullable=False, server_default="json"),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("source", sa.String(300), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_risk_config_config_key", "risk_config", ["config_key"], unique=True)

    # 种子数据：权威默认参数（source 多源互证）
    op.bulk_insert(
        sa.table(
            "risk_config",
            sa.column("config_key", sa.String),
            sa.column("config_value", SQLiteJSON()),
            sa.column("config_type", sa.String),
            sa.column("description", sa.String),
            sa.column("source", sa.String),
        ),
        SEED_CONFIG,
    )


def downgrade() -> None:
    op.drop_index("ix_risk_config_config_key", table_name="risk_config")
    op.drop_table("risk_config")
