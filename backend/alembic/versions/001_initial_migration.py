"""initial migration

Revision ID: 001
Revises:
Create Date: 2026-07-10

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 创建枚举类型 ──
    industry_type = sa.Enum('批发零售', '制造', '建筑', '电商', '餐饮服务', name='industry_type')
    risk_level = sa.Enum('low', 'medium', 'high', name='risk_level')
    direction_type = sa.Enum('inflow', 'outflow', name='direction_type')
    account_type = sa.Enum('corporate', 'personal', name='account_type')
    invoice_type = sa.Enum('input', 'output', name='invoice_type')
    tax_type = sa.Enum('vat', 'income_tax', 'personal_income_tax', name='tax_type')
    contract_type = sa.Enum('sales', 'purchase', name='contract_type')
    statement_type = sa.Enum('balance_sheet', 'income_statement', 'cash_flow', name='statement_type')
    assess_risk_level = sa.Enum('low', 'medium', 'high', name='assess_risk_level')
    task_priority = sa.Enum('high', 'medium', 'low', name='task_priority')
    task_status = sa.Enum('pending', 'in_progress', 'completed', name='task_status')

    industry_type.create(op.get_bind(), checkfirst=True)
    risk_level.create(op.get_bind(), checkfirst=True)
    direction_type.create(op.get_bind(), checkfirst=True)
    account_type.create(op.get_bind(), checkfirst=True)
    invoice_type.create(op.get_bind(), checkfirst=True)
    tax_type.create(op.get_bind(), checkfirst=True)
    contract_type.create(op.get_bind(), checkfirst=True)
    statement_type.create(op.get_bind(), checkfirst=True)
    assess_risk_level.create(op.get_bind(), checkfirst=True)
    task_priority.create(op.get_bind(), checkfirst=True)
    task_status.create(op.get_bind(), checkfirst=True)

    # ── enterprises（企业信息表） ──
    op.create_table(
        'enterprises',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False, comment='企业名称'),
        sa.Column('credit_code', sa.String(18), unique=True, nullable=False, comment='统一社会信用代码'),
        sa.Column('industry', postgresql.ENUM('批发零售', '制造', '建筑', '电商', '餐饮服务',
                  name='industry_type', create_type=False), nullable=False, comment='行业类型'),
        sa.Column('revenue_annual', sa.Numeric(15, 2), default=0, comment='年营收'),
        sa.Column('employee_count', sa.Integer, default=0, comment='员工人数'),
        sa.Column('tax_rate_industry', sa.Numeric(5, 2), default=0, comment='行业平均税负率'),
        sa.Column('cost_rate_industry', sa.Numeric(5, 2), default=0, comment='行业平均成本费用率'),
        sa.Column('is_high_tech', sa.Boolean, default=False, comment='是否高新技术企业'),
        sa.Column('is_small_micro', sa.Boolean, default=True, comment='是否小微企业'),
        sa.Column('risk_level', postgresql.ENUM('low', 'medium', 'high',
                  name='risk_level', create_type=False), nullable=False, server_default='low', comment='当前风险等级'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), comment='更新时间'),
    )

    # ── bank_transactions（银行流水表） ──
    op.create_table(
        'bank_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('transaction_date', sa.Date, nullable=False, comment='交易日期'),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False, comment='交易金额'),
        sa.Column('direction', postgresql.ENUM('inflow', 'outflow',
                  name='direction_type', create_type=False), nullable=False, comment='方向'),
        sa.Column('account_type', postgresql.ENUM('corporate', 'personal',
                  name='account_type', create_type=False), nullable=False, comment='账户类型'),
        sa.Column('account_holder', sa.String(100), comment='账户持有人'),
        sa.Column('counterparty', sa.String(200), comment='交易对手'),
        sa.Column('description', sa.String(500), comment='交易摘要'),
        sa.Column('is_declared', sa.Boolean, default=False, comment='是否已申报纳税'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── invoices（发票数据表） ──
    op.create_table(
        'invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('invoice_no', sa.String(50), nullable=False, comment='发票号码'),
        sa.Column('invoice_type', postgresql.ENUM('input', 'output',
                  name='invoice_type', create_type=False), nullable=False, comment='发票类型'),
        sa.Column('invoice_date', sa.Date, nullable=False, comment='开票日期'),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False, comment='金额'),
        sa.Column('tax_amount', sa.Numeric(15, 2), default=0, comment='税额'),
        sa.Column('total_amount', sa.Numeric(15, 2), nullable=False, comment='价税合计'),
        sa.Column('product_name', sa.String(200), comment='商品/服务名称'),
        sa.Column('buyer_name', sa.String(200), comment='购方名称'),
        sa.Column('seller_name', sa.String(200), comment='销方名称'),
        sa.Column('is_digital', sa.Boolean, default=False, comment='是否数电票'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── tax_declarations（纳税申报表） ──
    op.create_table(
        'tax_declarations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('tax_type', postgresql.ENUM('vat', 'income_tax', 'personal_income_tax',
                  name='tax_type', create_type=False), nullable=False, comment='税种'),
        sa.Column('period', sa.String(20), nullable=False, comment='申报期间'),
        sa.Column('declared_revenue', sa.Numeric(15, 2), default=0, comment='申报收入'),
        sa.Column('declared_tax', sa.Numeric(15, 2), default=0, comment='申报税额'),
        sa.Column('actual_paid', sa.Numeric(15, 2), default=0, comment='实际缴纳'),
        sa.Column('declaration_date', sa.Date, nullable=True, comment='申报日期'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── contracts（合同台账表） ──
    op.create_table(
        'contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('contract_no', sa.String(100), nullable=False, comment='合同编号'),
        sa.Column('contract_type', postgresql.ENUM('sales', 'purchase',
                  name='contract_type', create_type=False), nullable=False, comment='合同类型'),
        sa.Column('counterparty', sa.String(200), nullable=False, comment='合同对方'),
        sa.Column('contract_amount', sa.Numeric(15, 2), nullable=False, comment='合同金额'),
        sa.Column('signing_date', sa.Date, nullable=False, comment='签订日期'),
        sa.Column('execution_status', sa.String(50), default='进行中', comment='执行状态'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── financial_statements（财务报表表） ──
    op.create_table(
        'financial_statements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('period', sa.String(20), nullable=False, comment='报表期间'),
        sa.Column('statement_type', postgresql.ENUM('balance_sheet', 'income_statement', 'cash_flow',
                  name='statement_type', create_type=False), nullable=False, comment='报表类型'),
        sa.Column('total_assets', sa.Numeric(15, 2), default=0, comment='总资产'),
        sa.Column('total_revenue', sa.Numeric(15, 2), default=0, comment='营业收入'),
        sa.Column('total_cost', sa.Numeric(15, 2), default=0, comment='总成本费用'),
        sa.Column('net_profit', sa.Numeric(15, 2), default=0, comment='净利润'),
        sa.Column('operating_cash_flow', sa.Numeric(15, 2), default=0, comment='经营活动现金流'),
        sa.Column('tax_burden_rate', sa.Numeric(5, 2), default=0, comment='税负率'),
        sa.Column('cost_rate', sa.Numeric(5, 2), default=0, comment='成本费用率'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── risk_assessments（风险评估结果表） ──
    op.create_table(
        'risk_assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('assessment_date', sa.DateTime(timezone=True), nullable=False, comment='评估日期'),
        sa.Column('overall_risk_level', postgresql.ENUM('low', 'medium', 'high',
                  name='assess_risk_level', create_type=False), nullable=False, comment='总体风险等级'),
        sa.Column('overall_risk_score', sa.Numeric(5, 2), nullable=False, comment='总体风险评分'),
        sa.Column('four_flow_match_score', sa.Numeric(5, 2), default=0, comment='四流匹配度'),
        sa.Column('private_card_ratio', sa.Numeric(5, 2), default=0, comment='私卡收款占比'),
        sa.Column('cost_deviation', sa.Numeric(5, 2), default=0, comment='成本费用率偏离度'),
        sa.Column('risk_details', postgresql.JSONB, default=dict, comment='各维度风险详情'),
        sa.Column('recommendations', postgresql.JSONB, default=dict, comment='整改建议'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── psychological_profiles（心理画像表） ──
    op.create_table(
        'psychological_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('assessment_date', sa.DateTime(timezone=True), nullable=False, comment='评估日期'),
        sa.Column('control_desire_score', sa.Integer, default=0, comment='掌控欲得分'),
        sa.Column('loss_aversion_score', sa.Integer, default=0, comment='损失厌恶得分'),
        sa.Column('optimism_bias_score', sa.Integer, default=0, comment='乐观偏差得分'),
        sa.Column('control_illusion_score', sa.Integer, default=0, comment='控制错觉得分'),
        sa.Column('short_termism_score', sa.Integer, default=0, comment='短期主义得分'),
        sa.Column('defensiveness_score', sa.Integer, default=0, comment='防御心理得分'),
        sa.Column('deviation_index', sa.Numeric(5, 2), default=0, comment='偏差指数'),
        sa.Column('dominant_biases', postgresql.JSONB, default=list, comment='主导偏差类型列表'),
        sa.Column('intervention_strategy', postgresql.JSONB, default=dict, comment='干预策略推荐'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── remediation_tasks（整改任务表） ──
    op.create_table(
        'remediation_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('enterprise_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('enterprises.id', ondelete='CASCADE'), nullable=False, comment='企业ID'),
        sa.Column('risk_assessment_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('risk_assessments.id', ondelete='SET NULL'), nullable=True, comment='关联风险评估ID'),
        sa.Column('title', sa.String(200), nullable=False, comment='整改任务标题'),
        sa.Column('description', sa.String(2000), default='', comment='任务描述'),
        sa.Column('priority', postgresql.ENUM('high', 'medium', 'low',
                  name='task_priority', create_type=False), default='medium', nullable=False, comment='优先级'),
        sa.Column('status', postgresql.ENUM('pending', 'in_progress', 'completed',
                  name='task_status', create_type=False), default='pending', nullable=False, comment='状态'),
        sa.Column('due_date', sa.Date, nullable=True, comment='截止日期'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='完成时间'),
        sa.Column('progress', sa.Numeric(5, 2), default=0, comment='进度百分比'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 创建索引
    op.create_index('ix_bank_transactions_enterprise_id', 'bank_transactions', ['enterprise_id'])
    op.create_index('ix_invoices_enterprise_id', 'invoices', ['enterprise_id'])
    op.create_index('ix_tax_declarations_enterprise_id', 'tax_declarations', ['enterprise_id'])
    op.create_index('ix_contracts_enterprise_id', 'contracts', ['enterprise_id'])
    op.create_index('ix_financial_statements_enterprise_id', 'financial_statements', ['enterprise_id'])
    op.create_index('ix_risk_assessments_enterprise_id', 'risk_assessments', ['enterprise_id'])
    op.create_index('ix_psychological_profiles_enterprise_id', 'psychological_profiles', ['enterprise_id'])
    op.create_index('ix_remediation_tasks_enterprise_id', 'remediation_tasks', ['enterprise_id'])


def downgrade() -> None:
    op.drop_index('ix_remediation_tasks_enterprise_id', table_name='remediation_tasks')
    op.drop_index('ix_psychological_profiles_enterprise_id', table_name='psychological_profiles')
    op.drop_index('ix_risk_assessments_enterprise_id', table_name='risk_assessments')
    op.drop_index('ix_financial_statements_enterprise_id', table_name='financial_statements')
    op.drop_index('ix_contracts_enterprise_id', table_name='contracts')
    op.drop_index('ix_tax_declarations_enterprise_id', table_name='tax_declarations')
    op.drop_index('ix_invoices_enterprise_id', table_name='invoices')
    op.drop_index('ix_bank_transactions_enterprise_id', table_name='bank_transactions')

    op.drop_table('remediation_tasks')
    op.drop_table('psychological_profiles')
    op.drop_table('risk_assessments')
    op.drop_table('financial_statements')
    op.drop_table('contracts')
    op.drop_table('tax_declarations')
    op.drop_table('invoices')
    op.drop_table('bank_transactions')
    op.drop_table('enterprises')

    # 删除枚举类型
    sa.Enum(name='task_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='task_priority').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='assess_risk_level').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='statement_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='contract_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='tax_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='invoice_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='direction_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='account_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='risk_level').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='industry_type').drop(op.get_bind(), checkfirst=True)
