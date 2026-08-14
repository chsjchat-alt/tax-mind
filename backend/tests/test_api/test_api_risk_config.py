"""参数配置 API 测试（B1：GET 查看 / PUT 更新，RBAC 与缓存联动）"""
import pytest
import pytest_asyncio
import httpx

from app.core.cache import risk_scan_cache
from app.models.risk_config import RiskConfig


class TestRiskConfigApi:
    @pytest.mark.asyncio
    async def test_get_config_returns_all_items_with_sources(
        self, client: httpx.AsyncClient,
    ):
        """GET /api/v1/risk-config → 全量参数 + 权威来源标注"""
        resp = await client.get("/api/v1/risk-config")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total"] >= 15
        keys = {item["config_key"] for item in body["items"]}
        assert {"weights_7dim", "penalty_multiplier", "reduction_pct_max"} <= keys
        # 每个参数带权威来源（多源互证要求）
        for item in body["items"]:
            assert item["source"], item["config_key"]
            assert "config_value" in item

    @pytest.mark.asyncio
    async def test_put_updates_config_and_reflected_on_get(
        self, client: httpx.AsyncClient, db_session,
    ):
        """PUT 更新阈值 → GET 反映新值，且写入 risk_config 表"""
        resp = await client.put(
            "/api/v1/risk-config", json={"risk_high_threshold": 55.0}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["updated"] == {"risk_high_threshold": 55.0}

        resp2 = await client.get("/api/v1/risk-config")
        items = {i["config_key"]: i for i in resp2.json()["data"]["items"]}
        assert items["risk_high_threshold"]["config_value"] == 55.0

        # DB 落库（含权威来源与更新人）
        from sqlalchemy import select
        row = (
            await db_session.execute(
                select(RiskConfig).where(RiskConfig.config_key == "risk_high_threshold")
            )
        ).scalar_one_or_none()
        assert row is not None
        assert row.config_value == 55.0
        assert row.source

    @pytest.mark.asyncio
    async def test_put_unknown_key_rejected(
        self, client: httpx.AsyncClient,
    ):
        """未知配置键 → 40001 拒绝"""
        resp = await client.put("/api/v1/risk-config", json={"hack_key": 1})
        assert resp.status_code == 200
        assert resp.json()["code"] == 40001

    @pytest.mark.asyncio
    async def test_put_requires_admin(
        self, client: httpx.AsyncClient, db_session, auth_env,
    ):
        """非管理员 PUT → 403

        RBAC 校验在 require_admin 依赖内部执行（check_role），
        因此不能直接覆盖 require_admin 返回 viewer（会绕过校验），
        而应以抛 403 的桩函数覆盖，模拟真实权限拒绝路径。
        """
        from fastapi import HTTPException
        from app import main as app_main
        from app.api import deps as api_deps
        from app.models.user import User

        async def _deny_admin() -> User:
            raise HTTPException(status_code=403, detail="Admin only")

        app_main.app.dependency_overrides[api_deps.require_admin] = _deny_admin
        try:
            resp = await client.put(
                "/api/v1/risk-config", json={"risk_high_threshold": 10.0}
            )
            assert resp.status_code == 403
            # 配置未被修改
            resp2 = await client.get("/api/v1/risk-config")
            items = {i["config_key"]: i for i in resp2.json()["data"]["items"]}
            assert items["risk_high_threshold"]["config_value"] != 10.0
        finally:
            app_main.app.dependency_overrides.pop(api_deps.require_admin, None)

    @pytest.mark.asyncio
    async def test_config_update_invalidates_scan_cache(
        self, client: httpx.AsyncClient,
    ):
        """PUT 配置 → risk_scan_cache 全量失效（下次扫描按新参数重算）"""
        await risk_scan_cache.set("scan:test-ent", {"cached": True})
        resp = await client.put(
            "/api/v1/risk-config", json={"risk_medium_threshold": 35.0}
        )
        assert resp.status_code == 200
        assert await risk_scan_cache.get("scan:test-ent") is None
