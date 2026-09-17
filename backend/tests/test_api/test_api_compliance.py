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
    monkeypatch.setattr(app_main, "_write_audit_log", _noop_audit_log)
    yield tenant_id
    app.dependency_overrides.pop(compliance_api.get_current_tenant_id, None)
    app.dependency_overrides.pop(compliance_api.require_viewer, None)


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
