"""整改任务人工验证 API 测试（V4 §3.2 整改率分子认定，Q3/Q5）

口径：
  - 仅 COMPLETED 任务可验证；验证后计入整改率分子（权重比口径）；
  - RBAC：require_admin_or_auditor（viewer 拒绝）；
  - 重复验证 → 更新验证人与备注（纠正留痕）；
  - 任务重置为非完成状态 → 验证自动失效（PUT 联动）。
"""
import uuid

import pytest
import pytest_asyncio
import httpx

from app.models.remediation_task import RemediationTask, TaskStatus, TaskPriority


@pytest_asyncio.fixture
async def compliance_task(db_session, test_enterprise):
    """创建一个已完成（未验证）的合规整改任务"""
    task = RemediationTask(
        id=str(uuid.uuid4()),
        enterprise_id=test_enterprise.id,
        title="补齐进项税额转出凭证",
        description="合规校验自动生成",
        priority=TaskPriority.HIGH,
        status=TaskStatus.COMPLETED,
        source="compliance",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


class TestVerifyRemediationTask:
    @pytest.mark.asyncio
    async def test_verify_completed_task_success(
        self, client: httpx.AsyncClient, compliance_task, auth_env,
    ):
        """已完成任务 → 验证成功：verified_by/at/note 留痕"""
        resp = await client.post(
            f"/api/v1/remediation-tasks/{compliance_task.id}/verify",
            json={"note": "凭证已补齐，抽查无误"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["verified_at"] is not None
        assert data["verified_by"] == str(auth_env["user"].id)
        assert data["verify_note"] == "凭证已补齐，抽查无误"

    @pytest.mark.asyncio
    async def test_verify_non_completed_rejected(
        self, client: httpx.AsyncClient, db_session, test_enterprise,
    ):
        """未完成任务 → 40001 拒绝（Q5：部分整改不计）"""
        task = RemediationTask(
            id=str(uuid.uuid4()),
            enterprise_id=test_enterprise.id,
            title="进行中任务", description="",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.IN_PROGRESS,
            source="compliance",
        )
        db_session.add(task)
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/remediation-tasks/{task.id}/verify", json={},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 40001

    @pytest.mark.asyncio
    async def test_verify_not_found(self, client: httpx.AsyncClient):
        """任务不存在 → 40001"""
        resp = await client.post(
            f"/api/v1/remediation-tasks/{uuid.uuid4()}/verify", json={},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 40001

    @pytest.mark.asyncio
    async def test_reverify_updates_note(
        self, client: httpx.AsyncClient, compliance_task,
    ):
        """重复验证 → 更新备注（纠正留痕，幂等不报错）"""
        r1 = await client.post(
            f"/api/v1/remediation-tasks/{compliance_task.id}/verify",
            json={"note": "首次确认"},
        )
        assert r1.json()["code"] == 200
        r2 = await client.post(
            f"/api/v1/remediation-tasks/{compliance_task.id}/verify",
            json={"note": "复核后修正"},
        )
        body = r2.json()
        assert body["code"] == 200
        assert body["message"] == "验证信息已更新"
        assert body["data"]["verify_note"] == "复核后修正"

    @pytest.mark.asyncio
    async def test_reset_status_clears_verification(
        self, client: httpx.AsyncClient, compliance_task,
    ):
        """已完成 → 重置 in_progress：验证自动失效（防口径漏洞）"""
        r1 = await client.post(
            f"/api/v1/remediation-tasks/{compliance_task.id}/verify",
            json={"note": "确认"},
        )
        assert r1.json()["data"]["verified_at"] is not None

        r2 = await client.put(
            f"/api/v1/remediation-tasks/{compliance_task.id}",
            json={"status": "in_progress"},
        )
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert data["status"] == "in_progress"
        assert data["verified_at"] is None
        assert data["verified_by"] is None
        assert data["verify_note"] is None

    @pytest.mark.asyncio
    async def test_verify_requires_admin_or_auditor(
        self, client: httpx.AsyncClient, compliance_task,
    ):
        """RBAC：viewer 角色验证 → 403（Q3：admin/auditor 单确认）"""
        from fastapi import HTTPException
        from app import main as app_main
        from app.api import deps as api_deps

        async def _deny():
            raise HTTPException(status_code=403, detail="Admin or auditor only")

        app_main.app.dependency_overrides[api_deps.require_admin_or_auditor] = _deny
        try:
            resp = await client.post(
                f"/api/v1/remediation-tasks/{compliance_task.id}/verify",
                json={},
            )
            assert resp.status_code == 403
        finally:
            app_main.app.dependency_overrides.pop(
                api_deps.require_admin_or_auditor, None,
            )
