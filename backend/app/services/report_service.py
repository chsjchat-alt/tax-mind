"""
报告服务层

封装报告聚合生成逻辑。
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise
from app.models.risk_assessment import RiskAssessment
from app.models.psychological_profile import PsychologicalProfile


class ReportService:
    """报告生成服务"""

    @staticmethod
    async def generate_report(
        db: AsyncSession,
        enterprise_id: str,
        include_profile: bool = True,
        include_simulation: bool = True,
    ) -> dict:
        """生成企业风险评估报告（聚合风险+画像+模拟数据）"""
        result = await db.execute(
            select(Enterprise).where(Enterprise.id == enterprise_id)
        )
        enterprise = result.scalar_one_or_none()
        if not enterprise:
            raise ValueError(f"企业不存在: {enterprise_id}")

        # 最新风险评估
        risk_result = await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.enterprise_id == enterprise_id
            ).order_by(RiskAssessment.assessment_date.desc()).limit(1)
        )
        latest_risk = risk_result.scalar_one_or_none()

        # 最新心理画像
        latest_profile = None
        if include_profile:
            profile_result = await db.execute(
                select(PsychologicalProfile).where(
                    PsychologicalProfile.enterprise_id == enterprise_id
                ).order_by(PsychologicalProfile.assessment_date.desc()).limit(1)
            )
            latest_profile = profile_result.scalar_one_or_none()

        report_content = {
            "enterprise": {
                "id": str(enterprise.id),
                "name": enterprise.name,
                "industry": str(enterprise.industry),
                "revenue_annual": float(enterprise.revenue_annual or 0),
                "employee_count": enterprise.employee_count,
                "is_small_micro": enterprise.is_small_micro,
                "is_high_tech": enterprise.is_high_tech,
            },
            "risk_assessment": None,
            "profile": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "本报告基于模拟数据生成，仅供演示参考，不构成任何税务或法律建议。",
        }

        if latest_risk:
            report_content["risk_assessment"] = {
                "id": str(latest_risk.id),
                "level": latest_risk.overall_risk_level.value if latest_risk.overall_risk_level else "low",
                "score": float(latest_risk.overall_risk_score),
                "four_flow_match": float(latest_risk.four_flow_match_score),
                "private_card_ratio": float(latest_risk.private_card_ratio),
                "cost_deviation": float(latest_risk.cost_deviation),
                "dimensions": (latest_risk.risk_details or {}).get("dimension_scores", {}),
                "recommendations": latest_risk.recommendations or {},
                "date": latest_risk.assessment_date.isoformat() if latest_risk.assessment_date else None,
            }

        if latest_profile:
            report_content["profile"] = {
                "id": str(latest_profile.id),
                "deviation_index": float(latest_profile.deviation_index),
                "scores": {
                    "control_desire": latest_profile.control_desire_score,
                    "loss_aversion": latest_profile.loss_aversion_score,
                    "optimism_bias": latest_profile.optimism_bias_score,
                    "control_illusion": latest_profile.control_illusion_score,
                    "short_termism": latest_profile.short_termism_score,
                    "defensiveness": latest_profile.defensiveness_score,
                },
                "dominant_biases": latest_profile.dominant_biases,
                "intervention_strategy": latest_profile.intervention_strategy,
                "date": latest_profile.assessment_date.isoformat() if latest_profile.assessment_date else None,
            }

        report = {
            "id": str(uuid4()),
            "enterprise_id": str(enterprise_id),
            "title": f"{enterprise.name} - 财税合规风险评估报告",
            "report_type": "comprehensive",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content": report_content,
            "content_summary": {
                "risk_level": latest_risk.overall_risk_level.value if latest_risk.overall_risk_level else "low",
                "deviation_index": float(latest_profile.deviation_index) if latest_profile else 0,
            },
        }
        return report


report_service = ReportService()
