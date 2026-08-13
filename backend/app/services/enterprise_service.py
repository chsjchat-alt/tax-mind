"""
浼佷笟绠＄悊鏈嶅姟灞?

灏佽浼佷笟 CRUD 鎿嶄綔鍜屾暟鎹粺璁￠€昏緫銆?
"""
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise
from app.models.bank_transaction import BankTransaction
from app.models.invoice import Invoice
from app.models.tax_declaration import TaxDeclaration
from app.models.contract import Contract
from app.models.financial_statement import FinancialStatement
from app.models.risk_assessment import RiskAssessment
from app.schemas.enterprise import EnterpriseCreate, EnterpriseUpdate


class EnterpriseService:
    """浼佷笟 CRUD 鏈嶅姟"""

    @staticmethod
    async def list_enterprises(
        db: AsyncSession,
        industry: str | None = None,
        risk_level: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Enterprise], int]:
        """鑾峰彇浼佷笟鍒楄〃"""
        query = select(Enterprise).order_by(Enterprise.created_at.desc())
        if industry:
            query = query.where(Enterprise.industry == industry)
        if risk_level:
            query = query.where(Enterprise.risk_level == risk_level)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_enterprise(db: AsyncSession, enterprise_id: str) -> Enterprise | None:
        """鑾峰彇鍗曚釜浼佷笟"""
        result = await db.execute(
            select(Enterprise).where(Enterprise.id == enterprise_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_enterprise_stats(db: AsyncSession, enterprise_id: str) -> dict:
        """鑾峰彇浼佷笟鏁版嵁缁熻"""
        stats = {}
        for model, label in [
            (BankTransaction, "bank_transactions"),
            (Invoice, "invoices"),
            (TaxDeclaration, "tax_declarations"),
            (Contract, "contracts"),
            (FinancialStatement, "financial_statements"),
            (RiskAssessment, "risk_assessments"),
        ]:
            cnt = (await db.execute(
                select(func.count()).select_from(
                    select(model).where(model.enterprise_id == enterprise_id).subquery()
                )
            )).scalar() or 0
            stats[label] = cnt
        return stats

    @staticmethod
    async def create_enterprise(
        db: AsyncSession, data: EnterpriseCreate
    ) -> tuple[Enterprise | None, str | None]:
        """鍒涘缓浼佷笟锛岃繑鍥?(浼佷笟瀵硅薄, 閿欒娑堟伅)"""
        existing = await db.execute(
            select(Enterprise).where(Enterprise.credit_code == data.credit_code)
        )
        if existing.scalar_one_or_none():
            return None, f"缁熶竴绀句細淇＄敤浠ｇ爜宸插瓨鍦? {data.credit_code}"

        enterprise = Enterprise(**data.model_dump())
        db.add(enterprise)
        await db.flush()
        await db.refresh(enterprise)
        return enterprise, None

    @staticmethod
    async def update_enterprise(
        db: AsyncSession, enterprise_id: str, data: EnterpriseUpdate
    ) -> tuple[Enterprise | None, str | None]:
        """鏇存柊浼佷笟锛岃繑鍥?(浼佷笟瀵硅薄, 閿欒娑堟伅)"""
        enterprise = await EnterpriseService.get_enterprise(db, enterprise_id)
        if not enterprise:
            return None, f"浼佷笟涓嶅瓨鍦? {enterprise_id}"

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(enterprise, key, value)

        await db.flush()
        await db.refresh(enterprise)
        return enterprise, None

    @staticmethod
    async def delete_enterprise(
        db: AsyncSession, enterprise_id: str
    ) -> tuple[bool, str | None]:
        """鍒犻櫎浼佷笟锛堢骇鑱旓級锛岃繑鍥?(鏄惁鎴愬姛, 閿欒娑堟伅)"""
        enterprise = await EnterpriseService.get_enterprise(db, enterprise_id)
        if not enterprise:
            return False, f"浼佷笟涓嶅瓨鍦? {enterprise_id}"

        await db.delete(enterprise)
        await db.flush()
        return True, None


enterprise_service = EnterpriseService()
