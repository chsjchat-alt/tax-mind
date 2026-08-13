"""
test_api 包共享 fixtures

策略：
  - 使用 sqlite+aiosqlite 文件数据库（避免 :memory: 连接池跨会话隔离问题）
  - 通过 DATABASE_URL 环境变量覆盖，BEFORE 任何 app 模块导入
  - session 级别建表/删表，function 级别提供独立 client 和 db_session
"""
import os
import uuid
import tempfile
import asyncio
from datetime import date
from decimal import Decimal

# ── 必须在导入 app 模块之前设置 DATABASE_URL ──
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"taxmind_test_api_{uuid.uuid4().hex[:8]}.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest
import pytest_asyncio
import httpx

from app.database import engine, Base, AsyncSessionLocal
from app.main import app


# ====================================================================
# Session 级别：建表 → 全部测试 → 删表 + 清理文件
# ====================================================================

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """创建全部数据库表结构（session 级别，所有测试共享同一 schema）"""
    # 触发所有 ORM 模型注册
    import app.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # 清理
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    # 删除临时数据库文件
    # Windows 下 aiosqlite 可能延迟释放文件句柄，删除需重试
    for _ in range(8):
        try:
            os.remove(TEST_DB_PATH)
            break
        except FileNotFoundError:
            break
        except PermissionError:
            await asyncio.sleep(0.5)


# ====================================================================
# Function 级别：独立 session + HTTP client
# ====================================================================

@pytest_asyncio.fixture
async def db_session():
    """提供独立数据库会话用于种子数据写入"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client():
    """httpx.AsyncClient（ASGI transport，不走网络）"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac


# ====================================================================
# 常用种子数据 helper fixtures
# ====================================================================

@pytest_asyncio.fixture
async def test_enterprise(db_session):
    """创建一个基础测试企业并持久化到 DB"""
    from app.models.enterprise import Enterprise, IndustryType

    ent = Enterprise(
        name="测试企业-API",
        credit_code=_rand_credit_code(),
        industry=IndustryType.WHOLESALE_RETAIL,
        revenue_annual=Decimal("5000000"),
        tax_rate_claimed=Decimal("0.03"),
        cost_rate_claimed=Decimal("0.80"),
        is_high_tech=False,
        is_small_micro=True,
    )
    db_session.add(ent)
    await db_session.commit()
    await db_session.refresh(ent)
    return ent


@pytest_asyncio.fixture
async def enterprise_with_full_data(db_session):
    """创建带完整关联数据（流水、发票、合同、申报、财报）的企业"""
    from app.models.enterprise import Enterprise, IndustryType
    from app.models.bank_transaction import BankTransaction, DirectionType, AccountType
    from app.models.invoice import Invoice, InvoiceType
    from app.models.contract import Contract, ContractType
    from app.models.tax_declaration import TaxDeclaration, TaxType
    from app.models.financial_statement import FinancialStatement, StatementType

    eid = str(uuid.uuid4())
    ent = Enterprise(
        id=eid,
        name="完整数据测试企业",
        credit_code=_rand_credit_code(),
        industry=IndustryType.MANUFACTURING,
        revenue_annual=Decimal("12000000"),
        tax_rate_claimed=Decimal("0.05"),
        cost_rate_claimed=Decimal("0.72"),
        is_high_tech=True,
        is_small_micro=False,
    )
    db_session.add(ent)

    # ── 银行流水：3 笔对公流入 + 2 笔私卡流入 + 2 笔流出 ──
    txs = [
        BankTransaction(enterprise_id=eid, transaction_date=date(2025, 3, 15),
                        amount=Decimal("300000"), direction=DirectionType.INFLOW,
                        account_type=AccountType.CORPORATE, counterparty="客户A",
                        description="货款", is_declared=True),
        BankTransaction(enterprise_id=eid, transaction_date=date(2025, 4, 10),
                        amount=Decimal("250000"), direction=DirectionType.INFLOW,
                        account_type=AccountType.CORPORATE, counterparty="客户B",
                        description="服务费", is_declared=True),
        BankTransaction(enterprise_id=eid, transaction_date=date(2025, 5, 8),
                        amount=Decimal("180000"), direction=DirectionType.INFLOW,
                        account_type=AccountType.CORPORATE, counterparty="客户C",
                        description="货款", is_declared=True),
        BankTransaction(enterprise_id=eid, transaction_date=date(2025, 4, 20),
                        amount=Decimal("80000"), direction=DirectionType.INFLOW,
                        account_type=AccountType.PERSONAL, counterparty="客户D",
                        description="私卡收款", is_declared=False),
        BankTransaction(enterprise_id=eid, transaction_date=date(2025, 5, 22),
                        amount=Decimal("120000"), direction=DirectionType.INFLOW,
                        account_type=AccountType.PERSONAL, counterparty="客户E",
                        description="私卡收款", is_declared=False),
        BankTransaction(enterprise_id=eid, transaction_date=date(2025, 3, 20),
                        amount=Decimal("50000"), direction=DirectionType.OUTFLOW,
                        account_type=AccountType.CORPORATE, counterparty="供应商X",
                        description="采购付款"),
    ]
    for tx in txs:
        db_session.add(tx)

    # ── 发票：2 进项 + 2 销项 ──
    invs = [
        Invoice(enterprise_id=eid, invoice_no="INV-001", invoice_type=InvoiceType.OUTPUT,
                invoice_date=date(2025, 3, 15), amount=Decimal("300000"),
                tax_amount=Decimal("39000"), total_amount=Decimal("339000"),
                buyer_name="客户A", seller_name="测试企业", product_name="产品A"),
        Invoice(enterprise_id=eid, invoice_no="INV-002", invoice_type=InvoiceType.OUTPUT,
                invoice_date=date(2025, 4, 10), amount=Decimal("250000"),
                tax_amount=Decimal("32500"), total_amount=Decimal("282500"),
                buyer_name="客户B", seller_name="测试企业", product_name="产品B"),
        Invoice(enterprise_id=eid, invoice_no="INV-003", invoice_type=InvoiceType.INPUT,
                invoice_date=date(2025, 3, 20), amount=Decimal("50000"),
                tax_amount=Decimal("6500"), total_amount=Decimal("56500"),
                buyer_name="测试企业", seller_name="供应商X", product_name="原材料"),
        Invoice(enterprise_id=eid, invoice_no="INV-004", invoice_type=InvoiceType.INPUT,
                invoice_date=date(2025, 5, 1), amount=Decimal("30000"),
                tax_amount=Decimal("3900"), total_amount=Decimal("33900"),
                buyer_name="测试企业", seller_name="供应商Y", product_name="辅料"),
    ]
    for inv in invs:
        db_session.add(inv)

    # ── 合同：2 份 ──
    cts = [
        Contract(enterprise_id=eid, contract_no="CT-2025-001", contract_type=ContractType.SALES,
                 counterparty="客户A", contract_amount=Decimal("300000"),
                 signing_date=date(2025, 2, 1), execution_status="已完成"),
        Contract(enterprise_id=eid, contract_no="CT-2025-002", contract_type=ContractType.SALES,
                 counterparty="客户B", contract_amount=Decimal("250000"),
                 signing_date=date(2025, 3, 1), execution_status="进行中"),
    ]
    for ct in cts:
        db_session.add(ct)

    # ── 纳税申报：2 期 ──
    decls = [
        TaxDeclaration(enterprise_id=eid, tax_type=TaxType.VAT, period="2025-Q1",
                       declared_revenue=Decimal("550000"), declared_tax=Decimal("71500"),
                       actual_paid=Decimal("71500"), declaration_date=date(2025, 4, 10)),
        TaxDeclaration(enterprise_id=eid, tax_type=TaxType.VAT, period="2025-Q2",
                       declared_revenue=Decimal("480000"), declared_tax=Decimal("62400"),
                       actual_paid=Decimal("62400"), declaration_date=date(2025, 7, 8)),
    ]
    for d in decls:
        db_session.add(d)

    # ── 财务报表：4 期 ──
    stmts = [
        FinancialStatement(enterprise_id=eid, period="2025-01", statement_type=StatementType.INCOME_STATEMENT,
                           total_revenue=Decimal("1100000"), total_cost=Decimal("800000"),
                           tax_burden_rate=Decimal("0.065"), cost_rate=Decimal("0.727"),
                           total_assets=Decimal("5000000"), total_liabilities=Decimal("2000000"),
                           net_profit=Decimal("150000"), operating_cash_flow=Decimal("200000")),
        FinancialStatement(enterprise_id=eid, period="2025-02", statement_type=StatementType.INCOME_STATEMENT,
                           total_revenue=Decimal("1000000"), total_cost=Decimal("720000"),
                           tax_burden_rate=Decimal("0.062"), cost_rate=Decimal("0.720"),
                           total_assets=Decimal("5100000"), total_liabilities=Decimal("1900000"),
                           net_profit=Decimal("140000"), operating_cash_flow=Decimal("180000")),
        FinancialStatement(enterprise_id=eid, period="2025-03", statement_type=StatementType.INCOME_STATEMENT,
                           total_revenue=Decimal("950000"), total_cost=Decimal("690000"),
                           tax_burden_rate=Decimal("0.060"), cost_rate=Decimal("0.726"),
                           total_assets=Decimal("5200000"), total_liabilities=Decimal("2100000"),
                           net_profit=Decimal("130000"), operating_cash_flow=Decimal("170000")),
        FinancialStatement(enterprise_id=eid, period="2025-04", statement_type=StatementType.INCOME_STATEMENT,
                           total_revenue=Decimal("1050000"), total_cost=Decimal("760000"),
                           tax_burden_rate=Decimal("0.058"), cost_rate=Decimal("0.724"),
                           total_assets=Decimal("5300000"), total_liabilities=Decimal("2000000"),
                           net_profit=Decimal("145000"), operating_cash_flow=Decimal("190000")),
    ]
    for s in stmts:
        db_session.add(s)

    await db_session.commit()
    await db_session.refresh(ent)
    return ent


# ====================================================================
# Helpers
# ====================================================================

def _rand_credit_code() -> str:
    """生成唯一 18 位社会信用代码（测试用）"""
    return "91" + str(uuid.uuid4().int)[:16]
