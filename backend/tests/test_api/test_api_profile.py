"""
API 层测试：心理画像 (POST /api/v1/enterprises/{id}/profile)

使用 httpx.AsyncClient + SQLite 内存数据库测试端点。

测试场景：
  1. 完整数据企业 → 画像生成成功，返回 ProfileResponse
  2. 基础数据企业 → 可生成画像（默认值场景）
  3. 不存在的企业 ID → 40001 错误
  4. 画像历史 → 可多期获取
"""
import pytest
from httpx import AsyncClient


class TestProfileSuccess:
    """成功场景"""

    @pytest.mark.asyncio
    async def test_profile_with_full_data(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """完整数据企业心理画像 → 200 + 六维得分"""
        eid = enterprise_with_full_data.id
        resp = await client.post(f"/api/v1/enterprises/{eid}/profile")

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["message"] == "success"
        data = body["data"]

        # 核心字段
        assert "profile_id" in data
        assert data["enterprise_id"] == eid
        assert "deviation_index" in data
        assert isinstance(data["deviation_index"], (int, float))
        # 六维得分（整数 0-100）
        for field in [
            "control_desire_score",
            "loss_aversion_score",
            "optimism_bias_score",
            "control_illusion_score",
            "short_termism_score",
            "defensiveness_score",
        ]:
            assert field in data
            assert isinstance(data[field], int)
            assert 0 <= data[field] <= 100

        # 主导偏差与干预策略
        assert isinstance(data["dominant_biases"], list)
        assert isinstance(data["intervention_strategy"], dict)
        # 商业叙事
        assert isinstance(data["business_narrative"], str)
        assert len(data["business_narrative"]) > 0
        # 技术摘要
        assert isinstance(data["technical_summary"], dict)
        assert "assessment_date" in data

    @pytest.mark.asyncio
    async def test_profile_minimal_data(
        self, client: AsyncClient, test_enterprise
    ):
        """仅有企业基本信息 → 可生成画像（默认值）"""
        eid = test_enterprise.id
        resp = await client.post(f"/api/v1/enterprises/{eid}/profile")

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["enterprise_id"] == eid
        # 所有得分应为有效范围内的整数
        assert 0 <= data["deviation_index"] <= 100

    @pytest.mark.asyncio
    async def test_profile_persists_to_db(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """画像生成后持久化到 PsychologicalProfile 表"""
        eid = enterprise_with_full_data.id
        resp = await client.post(f"/api/v1/enterprises/{eid}/profile")
        assert resp.status_code == 200
        body = resp.json()

        # 通过历史列表验证已保存
        history_resp = await client.get(f"/api/v1/enterprises/{eid}/profiles")
        assert history_resp.status_code == 200
        hist = history_resp.json()
        assert hist["data"]["total"] >= 1
        profile_ids = [p["id"] for p in hist["data"]["profiles"]]
        assert body["data"]["profile_id"] in profile_ids

    @pytest.mark.asyncio
    async def test_profile_history_multiple(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """生成两次画像后，历史列表应有 2 条"""
        eid = enterprise_with_full_data.id
        await client.post(f"/api/v1/enterprises/{eid}/profile")
        await client.post(f"/api/v1/enterprises/{eid}/profile")

        resp = await client.get(f"/api/v1/enterprises/{eid}/profiles")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] >= 2

    @pytest.mark.asyncio
    async def test_profile_latest(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """可获取最新画像"""
        eid = enterprise_with_full_data.id
        await client.post(f"/api/v1/enterprises/{eid}/profile")

        resp = await client.get(f"/api/v1/enterprises/{eid}/profiles/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["data"]["enterprise_id"] == eid


class TestProfileErrors:
    """错误场景"""

    @pytest.mark.asyncio
    async def test_profile_nonexistent_enterprise(self, client: AsyncClient):
        """不存在的企业 ID → 40001"""
        resp = await client.post("/api/v1/enterprises/ghost-id/profile")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 40001
        assert "不存在" in body["message"]

    @pytest.mark.asyncio
    async def test_profile_latest_empty(self, client: AsyncClient):
        """无画像记录时查询最新 → 40001"""
        import uuid
        eid = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/enterprises/{eid}/profiles/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 40001


class TestProfileEdgeCases:
    """边界场景"""

    @pytest.mark.asyncio
    async def test_profile_consistent_scores(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """两次画像生成 → 得分一致（相同数据）"""
        eid = enterprise_with_full_data.id
        r1 = await client.post(f"/api/v1/enterprises/{eid}/profile")
        r2 = await client.post(f"/api/v1/enterprises/{eid}/profile")

        assert r1.status_code == r2.status_code == 200
        d1 = r1.json()["data"]
        d2 = r2.json()["data"]

        # 六维得分应相同（确定性算法，相同数据 → 相同结果）
        score_fields = [
            "control_desire_score", "loss_aversion_score",
            "optimism_bias_score", "control_illusion_score",
            "short_termism_score", "defensiveness_score",
        ]
        for field in score_fields:
            assert d1[field] == d2[field], (
                f"{field}: {d1[field]} != {d2[field]}"
            )

        # 偏差指数应一致
        assert d1["deviation_index"] == d2["deviation_index"]
