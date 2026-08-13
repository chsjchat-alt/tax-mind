from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.api import compliance as compliance_api
from app import main as app_main
from app.main import app
from app.models.enterprise import Enterprise, IndustryType
from app.models.risk_assessment import AssessRiskLevel, RiskAssessment
from app.models.tenant import Tenant
from app.schemas.nbt_intervention import NBTInterventionResponse

@pytest.fixture(autouse=True)
def override_runtime_dependencies(monkeypatch):
    tenant_id = str(uuid.uuid4())

    async def _tenant_id_override() -> str:
        return tenant_id

    async def _role_override():
        return None

    async def _noop_audit_log(_: dict) -> None:
        return None

    app.dependency_overrides[compliance_api.get_current_tenant_id] = (
        _tenant_id_override
    )
    app.dependency_overrides[compliance_api.require_viewer] = _role_override
    app.dependency_overrides[compliance_api.require_auditor] = _role_override
    monkeypatch.setattr(app_main, "_write_audit_log", _noop_audit_log)
    yield tenant_id
    app.dependency_overrides.pop(compliance_api.get_current_tenant_id, None)
    app.dependency_overrides.pop(compliance_api.require_viewer, None)
    app.dependency_overrides.pop(compliance_api.require_auditor, None)


@pytest_asyncio.fixture
async def compliance_enterprise(db_session, override_runtime_dependencies) -> Enterprise:
    tenant = Tenant(
        id=override_runtime_dependencies,
        name=f"测试租户-合规-{uuid.uuid4().hex[:8]}",
        slug=f"compliance-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    enterprise = Enterprise(
        tenant_id=tenant.id,
        name="测试企业-合规接口",
        credit_code="91" + str(uuid.uuid4().int)[:16],
        industry=IndustryType.WHOLESALE_RETAIL,
        revenue_annual=Decimal("5000000"),
        employee_count=28,
        tax_rate_claimed=Decimal("0.03"),
        cost_rate_claimed=Decimal("0.80"),
        is_high_tech=False,
        is_small_micro=True,
    )
    db_session.add(tenant)
    db_session.add(enterprise)
    await db_session.commit()
    await db_session.refresh(enterprise)
    return enterprise


async def _seed_risk_assessment(
    db_session,
    enterprise_id: str,
    *,
    score: str = "72.5",
    level: AssessRiskLevel = AssessRiskLevel.HIGH,
    compound_penalty_exposure: str = "120000",
    risk_details: dict | None = None,
) -> RiskAssessment:
    assessment = RiskAssessment(
        enterprise_id=enterprise_id,
        assessment_date=datetime.now(timezone.utc),
        overall_risk_level=level,
        overall_risk_score=Decimal(score),
        compound_penalty_exposure=Decimal(compound_penalty_exposure),
        risk_details=risk_details or {
            "private_card_ratio": 82,
            "cost_deviation": 48,
        },
    )
    db_session.add(assessment)
    await db_session.commit()
    await db_session.refresh(assessment)
    return assessment


def _build_fake_nbt_response() -> NBTInterventionResponse:
    return NBTInterventionResponse.model_validate(
        {
            "nudge": {
                "risk_statement": "风险提示" * 20,
                "psychological_trigger": "心理触发" * 10,
                "visual_recommendation": "视觉建议" * 8,
            },
            "budge": {
                "loss_comparison": "损失比较" * 30,
                "rebuttal_narrative": "反驳叙事" * 15,
                "timeline_pressure": "时间压力" * 10,
            },
            "trudge": {
                "sop_title": "合规整改标准作业流程",
                "micro_tasks": [
                    {
                        "task_id": 1,
                        "task_name": "核对申报",
                        "action": "逐项核对近期申报数据并留痕",
                        "deadline": "3个工作日",
                        "evidence_required": "申报底稿与复核记录",
                    }
                ],
                "compliance_framework": "合规框架说明" * 10,
                "trust_building_closing": "信任建设收尾" * 10,
            },
            "metadata": {
                "model": "test-double",
            },
        }
    )


class TestComplianceAPI:
    @pytest.mark.asyncio
    async def test_tax_preference_success(
        self,
        client: AsyncClient,
        compliance_enterprise,
        db_session,
    ):
        await _seed_risk_assessment(
            db_session,
            compliance_enterprise.id,
            level=AssessRiskLevel.MEDIUM,
        )

        resp = await client.get(
            f"/api/v1/enterprises/{compliance_enterprise.id}/tax-preference"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["data"]["is_small_micro"] is True
        assert "compliance_risk_level" in body["data"]

    @pytest.mark.asyncio
    async def test_nbt_intervention_sanitizes_client_risk_data(
        self,
        client: AsyncClient,
        compliance_enterprise,
        db_session,
        monkeypatch,
    ):
        await _seed_risk_assessment(db_session, compliance_enterprise.id)
        captured: dict[str, dict] = {}

        async def _fake_generate(data: dict):
            captured["payload"] = data
            return _build_fake_nbt_response()

        monkeypatch.setattr(
            compliance_api.llm_intervention_service,
            "generate_nbt_intervention",
            _fake_generate,
        )

        resp = await client.post(
            f"/api/v1/enterprises/{compliance_enterprise.id}/nbt-intervention",
            json={
                "overall_risk_score": 91,
                "ignored_field": "should not pass through",
                "risk_factors": {
                    "note": "  高风险提示  " * 80,
                    "nested": {
                        "items": [
                            {"text": "  明细说明  " * 40},
                        ]
                    },
                },
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "dynamic_mix" in body["data"]

        payload = captured["payload"]
        assert "ignored_field" not in payload
        assert payload["overall_risk_score"] == 91
        assert len(payload["risk_factors"]["note"]) <= compliance_api.MAX_RISK_STRING_LENGTH
        assert (
            len(payload["risk_factors"]["nested"]["items"][0]["text"])
            <= compliance_api.MAX_RISK_STRING_LENGTH
        )
        assert "npt_mix" in payload

    @pytest.mark.asyncio
    async def test_self_audit_report_and_installment_simulation(
        self,
        client: AsyncClient,
        compliance_enterprise,
        db_session,
    ):
        await _seed_risk_assessment(
            db_session,
            compliance_enterprise.id,
            risk_details={
                "private_card_ratio": 88,
                "tax_burden_deviation": 36,
            },
            compound_penalty_exposure="180000",
        )

        report_resp = await client.get(
            f"/api/v1/enterprises/{compliance_enterprise.id}/self-audit-report"
        )
        assert report_resp.status_code == 200
        report_body = report_resp.json()
        assert report_body["code"] == 200
        assert report_body["data"]["findings_summary"]["total"] == 2
        assert "markdown_content" in report_body["data"]

        simulation_resp = await client.get(
            f"/api/v1/enterprises/{compliance_enterprise.id}/installment-simulation"
        )
        assert simulation_resp.status_code == 200
        simulation_body = simulation_resp.json()
        assert simulation_body["code"] == 200
        assert simulation_body["data"]["total_tax_due"] == 180000.0
        assert len(simulation_body["data"]["installments"]) == 3
