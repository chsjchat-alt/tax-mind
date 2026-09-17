"""
API 层测试：租户隔离（安全加固防回归）

背景：所有涉及 enterprise_id 的查询/写接口已统一复用
`get_enterprise_or_403(ent_id, current_user)` 依赖函数，
企业不属于当前用户租户时返回 HTTP 403。

测试场景：
  1. 同租户用户访问本租户企业 → 200
  2. 租户A用户访问租户B企业（risk-scan / remediation / upload）→ 403
  3. 通过 task_id / assessment_id 间接访问他租户企业 → 403
  4. 不存在的企业 → 403（避免跨租户探测企业存在性）
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.main import app
from app import main as app_main
from app.api import deps
from app.models.enterprise import Enterprise, IndustryType
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.risk_assessment import RiskAssessment, AssessRiskLevel
from app.models.remediation_task import RemediationTask, TaskPriority

# 所有端点实际注入的角色依赖（覆盖后返回指定 User）
_AUTH_DEPS = (
    deps.require_viewer,
    deps.require_auditor,
    deps.require_admin,
    deps.require_admin_or_auditor,
)


@pytest_asyncio.fixture
async def tenant_isolation_env(db_session, monkeypatch):
    """构造双租户环境：租户A/B、企业A/B、用户A/B，并支持切换当前登录用户。

    默认以租户A用户登录；测试中可通过 env["set_user"](user_b) 切换。
    """
    tenant_a = Tenant(
        id=str(uuid.uuid4()), name=f"租户A-{uuid.uuid4().hex[:8]}",
        slug=f"ta-{uuid.uuid4().hex[:8]}", is_active=True,
    )
    tenant_b = Tenant(
        id=str(uuid.uuid4()), name=f"租户B-{uuid.uuid4().hex[:8]}",
        slug=f"tb-{uuid.uuid4().hex[:8]}", is_active=True,
    )
    user_a = User(
        username=f"user_a_{uuid.uuid4().hex[:8]}",
        hashed_password="not-used", tenant_id=tenant_a.id,
        role=UserRole.ADMIN,
    )
    user_b = User(
        username=f"user_b_{uuid.uuid4().hex[:8]}",
        hashed_password="not-used", tenant_id=tenant_b.id,
        role=UserRole.ADMIN,
    )
    ent_a = Enterprise(
        tenant_id=tenant_a.id, name="企业A-租户隔离测试",
        credit_code=_rand_credit_code(),
        industry=IndustryType.WHOLESALE_RETAIL,
        revenue_annual=Decimal("5000000"),
        tax_rate_claimed=Decimal("0.03"),
        cost_rate_claimed=Decimal("0.80"),
        is_high_tech=False, is_small_micro=True,
    )
    ent_b = Enterprise(
        tenant_id=tenant_b.id, name="企业B-租户隔离测试",
        credit_code=_rand_credit_code(),
        industry=IndustryType.MANUFACTURING,
        revenue_annual=Decimal("8000000"),
        tax_rate_claimed=Decimal("0.05"),
        cost_rate_claimed=Decimal("0.70"),
        is_high_tech=True, is_small_micro=False,
    )
    db_session.add_all([tenant_a, tenant_b, user_a, user_b, ent_a, ent_b])
    await db_session.commit()
    for obj in (tenant_a, tenant_b, user_a, user_b, ent_a, ent_b):
        await db_session.refresh(obj)

    def _set_user(user: User) -> None:
        async def _override() -> User:
            return user

        for dep in _AUTH_DEPS:
            app.dependency_overrides[dep] = _override

    _set_user(user_a)

    async def _noop_audit_log(_: dict) -> None:
        return None

    monkeypatch.setattr(app_main, "_write_audit_log", _noop_audit_log)

    env = {
        "user_a": user_a, "user_b": user_b,
        "ent_a": ent_a, "ent_b": ent_b,
        "db": db_session,
        "set_user": _set_user,
    }
    yield env

    for dep in _AUTH_DEPS:
        app.dependency_overrides.pop(dep, None)


async def _seed_remediation_task(db, enterprise_id: str) -> RemediationTask:
    task = RemediationTask(
        enterprise_id=enterprise_id,
        title="租户隔离测试任务",
        priority=TaskPriority.MEDIUM,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def _seed_risk_assessment(db, enterprise_id: str) -> RiskAssessment:
    assessment = RiskAssessment(
        enterprise_id=enterprise_id,
        assessment_date=datetime.now(timezone.utc),
        overall_risk_level=AssessRiskLevel.MEDIUM,
        overall_risk_score=Decimal("40"),
        risk_details={"private_card_ratio": 10},
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment


class TestSameTenantAccess:
    """同租户访问应正常放行"""

    @pytest.mark.asyncio
    async def test_same_tenant_risk_scan_ok(
        self, client: AsyncClient, tenant_isolation_env
    ):
        env = tenant_isolation_env
        resp = await client.post(f"/api/v1/enterprises/{env['ent_a'].id}/risk-scan")
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    @pytest.mark.asyncio
    async def test_same_tenant_remediation_list_ok(
        self, client: AsyncClient, tenant_isolation_env
    ):
        env = tenant_isolation_env
        resp = await client.get(f"/api/v1/enterprises/{env['ent_a'].id}/remediation-tasks")
        assert resp.status_code == 200
        assert resp.json()["code"] == 200

    @pytest.mark.asyncio
    async def test_same_tenant_confirm_task_ok(
        self, client: AsyncClient, tenant_isolation_env
    ):
        """同租户可正常确认上传任务完成"""
        env = tenant_isolation_env
        task = await _seed_remediation_task(env["db"], env["ent_a"].id)
        resp = await client.post(
            f"/api/v1/enterprises/{env['ent_a'].id}/upload-documents/confirm-task",
            data={"task_id": task.id, "action": "complete"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 200


class TestCrossTenantForbidden:
    """跨租户访问企业资源 → 403"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,path", [
        ("post", "/api/v1/enterprises/{eid}/risk-scan"),
        ("get", "/api/v1/enterprises/{eid}/risk-assessments"),
        ("get", "/api/v1/enterprises/{eid}/risk-assessments/latest"),
        ("get", "/api/v1/enterprises/{eid}/remediation-tasks"),
    ])
    async def test_cross_tenant_enterprise_path_forbidden(
        self, client: AsyncClient, tenant_isolation_env, method, path
    ):
        """租户A用户访问租户B企业的路径端点 → 403"""
        env = tenant_isolation_env
        resp = await getattr(client, method)(path.format(eid=env["ent_b"].id))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_tenant_remediation_create_forbidden(
        self, client: AsyncClient, tenant_isolation_env
    ):
        env = tenant_isolation_env
        resp = await client.post(
            f"/api/v1/enterprises/{env['ent_b'].id}/remediation-tasks",
            json={"title": "越权任务"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_tenant_remediation_detail_forbidden(
        self, client: AsyncClient, tenant_isolation_env
    ):
        """通过 task_id 间接访问他租户任务 → 403"""
        env = tenant_isolation_env
        task = await _seed_remediation_task(env["db"], env["ent_b"].id)
        resp = await client.get(f"/api/v1/remediation-tasks/{task.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_tenant_remediation_update_forbidden(
        self, client: AsyncClient, tenant_isolation_env
    ):
        """通过 task_id 修改他租户任务 → 403"""
        env = tenant_isolation_env
        task = await _seed_remediation_task(env["db"], env["ent_b"].id)
        resp = await client.put(
            f"/api/v1/remediation-tasks/{task.id}",
            json={"status": "completed"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_tenant_risk_assessment_detail_forbidden(
        self, client: AsyncClient, tenant_isolation_env
    ):
        """通过 assessment_id 访问他租户评估 → 403"""
        env = tenant_isolation_env
        assessment = await _seed_risk_assessment(env["db"], env["ent_b"].id)
        resp = await client.get(f"/api/v1/risk-assessments/{assessment.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_tenant_confirm_task_forbidden(
        self, client: AsyncClient, tenant_isolation_env
    ):
        """confirm_task_from_upload 跨租户 → 403（核心漏洞点）"""
        env = tenant_isolation_env
        task = await _seed_remediation_task(env["db"], env["ent_b"].id)
        resp = await client.post(
            f"/api/v1/enterprises/{env['ent_b'].id}/upload-documents/confirm-task",
            data={"task_id": task.id, "action": "complete"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_tenant_upload_documents_forbidden(
        self, client: AsyncClient, tenant_isolation_env
    ):
        env = tenant_isolation_env
        resp = await client.post(
            f"/api/v1/enterprises/{env['ent_b'].id}/upload-documents",
            files={"file": (
                "test.xlsx", b"dummy",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_nonexistent_enterprise_forbidden(
        self, client: AsyncClient, tenant_isolation_env
    ):
        """不存在的企业 → 403（不泄露存在性）"""
        resp = await client.post(f"/api/v1/enterprises/{uuid.uuid4()}/risk-scan")
        assert resp.status_code == 403


def _rand_credit_code() -> str:
    """生成唯一 18 位社会信用代码（测试用）"""
    return "91" + str(uuid.uuid4().int)[:16]
