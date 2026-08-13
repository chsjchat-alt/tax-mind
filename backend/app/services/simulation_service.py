"""
风险模拟服务层

封装模拟运行和案例检索逻辑。
"""
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise
from app.models.risk_assessment import RiskAssessment
from app.core.simulation_engine import run_simulation, SimulationInput


class SimulationService:
    """风险模拟服务"""

    @staticmethod
    async def run_simulation(
        db: AsyncSession,
        enterprise_id: str,
        monthly_hidden_revenue: float,
        comprehensive_tax_rate: float,
        remediation_cost: float,
    ) -> dict:
        """运行风险模拟"""
        result = await db.execute(
            select(Enterprise).where(Enterprise.id == enterprise_id)
        )
        enterprise = result.scalar_one_or_none()
        if not enterprise:
            raise ValueError(f"企业不存在: {enterprise_id}")

        risk_level = "low"
        risk_result = await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.enterprise_id == enterprise_id
            ).order_by(RiskAssessment.assessment_date.desc()).limit(1)
        )
        latest = risk_result.scalar_one_or_none()
        if latest:
            risk_level = latest.overall_risk_level.value if latest.overall_risk_level else "low"

        sim_result = run_simulation(SimulationInput(
            monthly_hidden_revenue=monthly_hidden_revenue,
            comprehensive_tax_rate=comprehensive_tax_rate,
            risk_level=risk_level,
            remediation_cost=remediation_cost,
        ))

        return {
            "time_points": [
                {
                    "year": tp.year,
                    "hidden_cumulative": tp.hidden_cumulative,
                    "tax_gap_cumulative": tp.tax_gap_cumulative,
                    "penalty_exposure": tp.penalty_exposure,
                    "audit_probability": tp.audit_probability,
                }
                for tp in sim_result.time_points
            ],
            "recommendation": sim_result.recommendation,
            "loss_frame_message": sim_result.loss_frame_message,
            "technical_summary": sim_result.technical_summary,
            "case_references": sim_result.case_references or [],
        }

    @staticmethod
    def get_case_studies(
        industry: str | None = None,
        risk_level: str | None = None,
    ) -> dict:
        """获取案例库，支持筛选"""
        cases_path = Path(__file__).parent.parent / "data" / "case_studies.json"
        try:
            with open(cases_path, "r", encoding="utf-8") as f:
                all_cases = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            all_cases = []

        if isinstance(all_cases, dict):
            flat = []
            for key in all_cases:
                if isinstance(all_cases[key], list):
                    flat.extend(all_cases[key])
                elif isinstance(all_cases[key], dict):
                    for sub in all_cases[key].values():
                        if isinstance(sub, list):
                            flat.extend(sub)
            all_cases = flat

        if not isinstance(all_cases, list):
            all_cases = []

        filtered = []
        for case in all_cases:
            if industry and case.get("industry") != industry:
                continue
            if risk_level and case.get("risk_level") != risk_level:
                continue
            filtered.append({
                "case_id": case.get("case_id", case.get("id", "")),
                "industry": case.get("industry", ""),
                "risk_level": case.get("risk_level", ""),
                "title": case.get("title", ""),
                "summary": case.get("summary", ""),
                "key_findings": case.get("key_findings", []),
                "outcome": case.get("outcome", ""),
            })

        return {"cases": filtered, "total": len(filtered)}


simulation_service = SimulationService()
