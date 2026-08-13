"""
心理画像服务层

封装：从数据库查询行为变量 → 组装 ProfileInput → 调用 profile_engine → 存储结果
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise
from app.models.bank_transaction import BankTransaction
from app.models.tax_declaration import TaxDeclaration
from app.models.psychological_profile import PsychologicalProfile
from app.models.risk_assessment import RiskAssessment
from app.models.remediation_task import RemediationTask, TaskStatus
from app.core.profile_engine import calculate_psychological_profile, BehavioralData


class ProfileService:
    """心理画像服务"""

    @staticmethod
    async def build_behavioral_data(
        db: AsyncSession, enterprise: Enterprise
    ) -> BehavioralData:
        """从企业数据构建行为数据输入"""
        # 私卡占比
        tx_result = await db.execute(
            select(BankTransaction).where(BankTransaction.enterprise_id == enterprise.id)
        )
        transactions = list(tx_result.scalars().all())

        total_inflow = Decimal("0")
        private_inflow = Decimal("0")
        for tx in transactions:
            amt = Decimal(str(tx.amount))
            if tx.direction == "inflow":
                total_inflow += amt
                if tx.account_type == "personal":
                    private_inflow += amt
        private_ratio = float(private_inflow / total_inflow) if total_inflow > 0 else 0.0

        tax_burden_deviation = 0.0

        # 历史风险次数
        risk_count = (await db.execute(
            select(func.count()).select_from(
                select(RiskAssessment).where(
                    RiskAssessment.enterprise_id == enterprise.id
                ).subquery()
            )
        )).scalar() or 0

        # 高风险比例
        high_count = (await db.execute(
            select(func.count()).select_from(
                select(RiskAssessment).where(
                    RiskAssessment.enterprise_id == enterprise.id,
                    RiskAssessment.overall_risk_level == "high",
                ).subquery()
            )
        )).scalar() or 0
        risk_recurrence = high_count / risk_count if risk_count > 0 else 0.0

        # 连续高风险期数
        consecutive = 0
        if high_count > 0:
            recent = await db.execute(
                select(RiskAssessment).where(
                    RiskAssessment.enterprise_id == enterprise.id
                ).order_by(RiskAssessment.assessment_date.desc()).limit(4)
            )
            for r in recent.scalars().all():
                if (r.overall_risk_level.value if r.overall_risk_level else "low") == "high":
                    consecutive += 1

        # 整改任务完成率 = 已完成任务数 / 总任务数 * 100（无任务返回 0）
        total_tasks = (await db.execute(
            select(func.count()).select_from(
                select(RemediationTask).where(
                    RemediationTask.enterprise_id == enterprise.id
                ).subquery()
            )
        )).scalar() or 0
        completed_tasks = (await db.execute(
            select(func.count()).select_from(
                select(RemediationTask).where(
                    RemediationTask.enterprise_id == enterprise.id,
                    RemediationTask.status == TaskStatus.COMPLETED,
                ).subquery()
            )
        )).scalar() or 0
        remediation_rate = round(completed_tasks / total_tasks * 100, 2) if total_tasks > 0 else 0.0

        # 四流匹配度
        four_flow_score = 100.0
        latest_risk = await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.enterprise_id == enterprise.id
            ).order_by(RiskAssessment.assessment_date.desc()).limit(1)
        )
        latest = latest_risk.scalar_one_or_none()
        if latest:
            four_flow_score = latest.four_flow_match_score

        # 未申报收入占比
        dec_result = await db.execute(
            select(TaxDeclaration).where(TaxDeclaration.enterprise_id == enterprise.id)
        )
        declarations = dec_result.scalars().all()
        total_declared = sum(Decimal(str(d.declared_revenue)) for d in declarations)
        total_revenue = Decimal(str(enterprise.revenue_annual))
        undeclared_ratio = float(1 - total_declared / total_revenue) if total_revenue > 0 else 0.0
        undeclared_ratio = max(0.0, undeclared_ratio)

        return BehavioralData(
            private_card_ratio=private_ratio,
            tax_burden_deviation=tax_burden_deviation,
            historical_risk_count=risk_count,
            risk_recurrence_rate=risk_recurrence,
            four_flow_match_score=four_flow_score,
            undeclared_revenue_ratio=undeclared_ratio,
            remediation_completion_rate=remediation_rate,
            consecutive_high_risk_periods=consecutive,
            is_high_tech=enterprise.is_high_tech,
            is_small_micro=enterprise.is_small_micro,
            revenue_annual=enterprise.revenue_annual or 0,
        )

    @staticmethod
    async def save_profile(
        db: AsyncSession, enterprise_id: str, profile_result
    ) -> PsychologicalProfile:
        """保存心理画像"""
        profile = PsychologicalProfile(
            enterprise_id=enterprise_id,
            assessment_date=datetime.now(timezone.utc),
            control_desire_score=profile_result.control_desire_score,
            loss_aversion_score=profile_result.loss_aversion_score,
            optimism_bias_score=profile_result.optimism_bias_score,
            control_illusion_score=profile_result.control_illusion_score,
            short_termism_score=profile_result.short_termism_score,
            defensiveness_score=profile_result.defensiveness_score,
            deviation_index=profile_result.deviation_index,
            dominant_biases=profile_result.dominant_biases,
            intervention_strategy=profile_result.intervention_strategy,
        )
        db.add(profile)
        await db.flush()
        await db.refresh(profile)
        return profile

    @staticmethod
    async def list_profiles(
        db: AsyncSession, enterprise_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[PsychologicalProfile], int]:
        """获取心理画像历史"""
        query = select(PsychologicalProfile).where(
            PsychologicalProfile.enterprise_id == enterprise_id
        ).order_by(PsychologicalProfile.assessment_date.desc())

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_latest_profile(
        db: AsyncSession, enterprise_id: str
    ) -> PsychologicalProfile | None:
        """获取最新心理画像"""
        result = await db.execute(
            select(PsychologicalProfile).where(
                PsychologicalProfile.enterprise_id == enterprise_id
            ).order_by(PsychologicalProfile.assessment_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()


profile_service = ProfileService()
