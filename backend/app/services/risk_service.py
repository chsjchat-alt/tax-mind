"""
风险扫描服务层

封装：从数据库查询数据 → 组装风险引擎输入 → 调用 core/risk_engine → 存储结果
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise
from app.models.bank_transaction import BankTransaction
from app.models.invoice import Invoice
from app.models.tax_declaration import TaxDeclaration
from app.models.contract import Contract
from app.models.financial_statement import FinancialStatement
from app.models.risk_assessment import RiskAssessment, AssessRiskLevel
from app.models.risk_score_trajectory import RiskScoreTrajectory
from app.core.risk_engine import assess_enterprise_risk, EnterpriseRiskInput
from app.core.four_flow_match import (
    calculate_four_flow_match,
    ContractRecord, InvoiceRecord, BankTransactionRecord,
)


class RiskScanService:
    """风险扫描服务"""

    @staticmethod
    async def load_enterprise_data(
        db: AsyncSession, enterprise_id: str, tenant_id: str | None = None
    ) -> tuple[Enterprise | None, list, list, list, list]:
        """加载企业及其关联数据"""
        query = select(Enterprise).where(Enterprise.id == enterprise_id)
        if tenant_id:
            query = query.where(Enterprise.tenant_id == tenant_id)
        result = await db.execute(query)
        enterprise = result.scalar_one_or_none()
        if not enterprise:
            return None, [], [], [], []

        tx_result = await db.execute(
            select(BankTransaction).where(BankTransaction.enterprise_id == enterprise_id)
        )
        transactions = list(tx_result.scalars().all())

        inv_result = await db.execute(
            select(Invoice).where(Invoice.enterprise_id == enterprise_id)
        )
        invoices = list(inv_result.scalars().all())

        ct_result = await db.execute(
            select(Contract).where(Contract.enterprise_id == enterprise_id)
        )
        contracts = list(ct_result.scalars().all())

        dec_result = await db.execute(
            select(TaxDeclaration).where(TaxDeclaration.enterprise_id == enterprise_id)
        )
        declarations = list(dec_result.scalars().all())

        return enterprise, transactions, invoices, contracts, declarations

    @staticmethod
    def build_risk_input(
        enterprise: Enterprise,
        transactions: list,
        invoices: list,
        contracts: list,
        declarations: list,
    ) -> tuple:
        """从数据库数据构建风险引擎输入"""
        total_private = Decimal("0")
        for tx in transactions:
            if tx.direction == "inflow" and tx.account_type == "personal":
                total_private += Decimal(str(tx.amount))

        total_declared = Decimal("0")
        for d in declarations:
            total_declared += Decimal(str(d.declared_revenue))

        total_input = Decimal("0")
        total_output = Decimal("0")
        for inv in invoices:
            tax = Decimal(str(inv.tax_amount))
            if inv.invoice_type == "input":
                total_input += tax
            else:
                total_output += tax

        contract_records = [
            ContractRecord(
                contract_no=c.contract_no,
                counterparty=c.counterparty,
                amount=Decimal(str(c.contract_amount)),
                signing_date=c.signing_date,
            ) for c in contracts
        ]
        invoice_records = [
            InvoiceRecord(
                invoice_no=inv.invoice_no,
                invoice_type=inv.invoice_type,
                amount=Decimal(str(inv.amount)),
                total_amount=Decimal(str(inv.total_amount)),
                buyer_name=inv.buyer_name,
                seller_name=inv.seller_name,
                product_name=inv.product_name or "",
            ) for inv in invoices
        ]
        bank_records = [
            BankTransactionRecord(
                transaction_date=tx.transaction_date,
                amount=Decimal(str(tx.amount)),
                direction=tx.direction,
                account_type=tx.account_type,
                counterparty=tx.counterparty,
                description=tx.description or "",
                is_declared=tx.is_declared,
            ) for tx in transactions
        ]

        return EnterpriseRiskInput(
            enterprise_name=enterprise.name,
            industry=str(enterprise.industry),
            revenue_annual=Decimal(str(enterprise.revenue_annual)),
            tax_rate_industry=Decimal(str(enterprise.tax_rate_claimed)),
            cost_rate_industry=Decimal(str(enterprise.cost_rate_claimed)),
            actual_tax_burden_rate=Decimal("0"),
            actual_cost_rate=Decimal("0"),
            total_private_card_amount=total_private,
            total_revenue=total_declared if total_declared > 0 else Decimal(str(enterprise.revenue_annual)),
            total_input_invoice=total_input,
            total_output_invoice=total_output,
            tax_credit_level=enterprise.tax_credit_level,
            tax_crime_convicted=enterprise.tax_crime_convicted,
        ), contract_records, invoice_records, bank_records

    @staticmethod
    async def enrich_with_financials(
        db: AsyncSession, enterprise_id: str, risk_input: EnterpriseRiskInput,
    ):
        """补充财务报表数据到风险输入"""
        fs_result = await db.execute(
            select(FinancialStatement).where(
                FinancialStatement.enterprise_id == enterprise_id
            ).order_by(FinancialStatement.period.desc()).limit(4)
        )
        stmts = fs_result.scalars().all()
        if stmts:
            avg_tax = sum(s.tax_burden_rate for s in stmts if s.tax_burden_rate) / max(
                sum(1 for s in stmts if s.tax_burden_rate), 1
            )
            avg_cost = sum(s.cost_rate for s in stmts if s.cost_rate) / max(
                sum(1 for s in stmts if s.cost_rate), 1
            )
            risk_input.actual_tax_burden_rate = Decimal(str(round(float(avg_tax), 2)))
            risk_input.actual_cost_rate = Decimal(str(round(float(avg_cost), 2)))

    @staticmethod
    async def save_assessment(
        db: AsyncSession,
        enterprise_id: str,
        risk_result,
        ffm_result,
        risk_input: EnterpriseRiskInput,
        transactions: list,
    ) -> RiskAssessment:
        """保存风险评估结果"""
        assessment = RiskAssessment(
            enterprise_id=enterprise_id,
            assessment_date=datetime.now(timezone.utc),
            overall_risk_level=AssessRiskLevel(risk_result.overall_risk_level),
            overall_risk_score=risk_result.overall_risk_score,
            four_flow_match_score=ffm_result.overall_score,
            private_card_ratio=float(
                sum(Decimal(str(tx.amount)) for tx in transactions
                    if tx.direction == "inflow" and tx.account_type == "personal")
            ) / float(risk_input.total_revenue) if float(risk_input.total_revenue) > 0 else 0,
            cost_deviation=float(risk_input.actual_cost_rate) - float(risk_input.cost_rate_industry)
                if float(risk_input.actual_cost_rate) > 0 else 0,
            risk_details={
                "dimension_scores": risk_result.dimension_scores,
                "dim_details": risk_result.dim_details,
                "match_details": ffm_result.details,
                "business_narrative": risk_result.business_narrative,
                "technical_summary": risk_result.technical_summary,
            },
            recommendations={"flags": risk_result.risk_flags, "recommendations": risk_result.recommendations},
        )
        db.add(assessment)
        await db.flush()
        await db.refresh(assessment)
        return assessment

    @staticmethod
    def build_snapshot_from_assessment(
        assessment: RiskAssessment,
    ) -> dict:
        """从已落库的 RiskAssessment 构建完整快照（RiskSnapshotResponse 格式）"""
        risk_details = assessment.risk_details or {}
        return {
            "risk_assessment_id": assessment.id,
            "enterprise_id": assessment.enterprise_id,
            "overall_risk_level": assessment.overall_risk_level.value
                if isinstance(assessment.overall_risk_level, AssessRiskLevel)
                else assessment.overall_risk_level,
            "overall_risk_score": float(assessment.overall_risk_score),
            "four_flow_match_score": float(assessment.four_flow_match_score),
            "private_card_ratio": float(assessment.private_card_ratio),
            "cost_deviation": float(assessment.cost_deviation),
            "dimension_scores": risk_details.get("dimension_scores", {}),
            "dim_details": risk_details.get("dim_details", {}),
            "match_details": risk_details.get("match_details", []),
            "recommendations": assessment.recommendations or {},
            "business_narrative": risk_details.get("business_narrative", ""),
            "technical_summary": risk_details.get("technical_summary", {}),
            "assessment_date": assessment.assessment_date,
        }

    @staticmethod
    async def list_assessments(
        db: AsyncSession, enterprise_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[RiskAssessment], int]:
        """获取风险评估历史"""
        query = select(RiskAssessment).where(
            RiskAssessment.enterprise_id == enterprise_id
        ).order_by(RiskAssessment.assessment_date.desc())

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_latest_assessment(
        db: AsyncSession, enterprise_id: str
    ) -> RiskAssessment | None:
        """获取最新风险评估"""
        result = await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.enterprise_id == enterprise_id
            ).order_by(RiskAssessment.assessment_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_assessment_by_id(
        db: AsyncSession, assessment_id: str
    ) -> RiskAssessment | None:
        """按ID获取风险评估"""
        result = await db.execute(
            select(RiskAssessment).where(RiskAssessment.id == assessment_id)
        )
        return result.scalar_one_or_none()

    # ── 风险评分轨迹（B3 持久化，支撑整改前后演化展示）──

    @staticmethod
    def _level_jump(before_level: str | None, after_level: str) -> str:
        """根据前后等级确定跃迁方向（up 恶化 / down 改善 / same 不变）。"""
        order = {"low": 0, "medium": 1, "medium_high": 2, "high": 3, "critical": 4}
        before_idx = order.get(before_level or "low", 0)
        after_idx = order.get(after_level, 0)
        if after_idx > before_idx:
            return "up"
        if after_idx < before_idx:
            return "down"
        return "same"

    @staticmethod
    async def record_score_trajectory(
        db: AsyncSession,
        enterprise_id: str,
        after_score: float,
        after_level: str,
        changed_by: str,
        reason: str = "",
        before_score: float | None = None,
        before_level: str | None = None,
        assessment_date: datetime | None = None,
    ) -> RiskScoreTrajectory:
        """记录一条评分轨迹（整改完成 / 例行重评时调用）。"""
        trajectory = RiskScoreTrajectory(
            enterprise_id=enterprise_id,
            assessment_date=assessment_date or datetime.now(timezone.utc),
            before_score=(
                Decimal(str(round(before_score, 2)))
                if before_score is not None else None
            ),
            after_score=Decimal(str(round(after_score, 2))),
            before_level=before_level,
            after_level=after_level,
            level_jump=RiskScanService._level_jump(before_level, after_level),
            changed_by=changed_by,
            reason=reason[:500],
        )
        db.add(trajectory)
        await db.flush()
        await db.refresh(trajectory)
        return trajectory

    @staticmethod
    async def list_score_trajectory(
        db: AsyncSession, enterprise_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[RiskScoreTrajectory], int]:
        """获取企业的评分演化轨迹（按时间倒序）。"""
        query = select(RiskScoreTrajectory).where(
            RiskScoreTrajectory.enterprise_id == enterprise_id
        ).order_by(RiskScoreTrajectory.assessment_date.desc())

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        result = await db.execute(query.offset(offset).limit(limit))
        return list(result.scalars().all()), total


risk_scan_service = RiskScanService()
