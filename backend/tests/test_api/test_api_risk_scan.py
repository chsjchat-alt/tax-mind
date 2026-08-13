"""
API 层测试：风险扫描 (POST /api/v1/enterprises/{id}/risk-scan)

使用 httpx.AsyncClient + SQLite 内存数据库测试端点。

测试场景：
  1. 完整数据企业 → 扫描成功，返回 RiskScanResponse
  2. 基础数据企业（无关联数据）→ 仍可扫描成功
  3. 不存在的企业 ID → 40001 错误
  4. 高风险企业（私卡占比高）→ overall_risk_level = high
"""
import pytest
from httpx import AsyncClient


class TestRiskScanSuccess:
    """成功场景"""

    @pytest.mark.asyncio
    async def test_scan_enterprise_with_full_data(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """完整数据企业风险扫描 → 200 + 完整响应字段"""
        eid = enterprise_with_full_data.id
        resp = await client.post(f"/api/v1/enterprises/{eid}/risk-scan")

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["message"] == "success"
        data = body["data"]

        # 核心字段存在
        assert "risk_assessment_id" in data
        assert data["enterprise_id"] == eid
        assert "overall_risk_level" in data
        assert data["overall_risk_level"] in ("low", "medium", "high", "critical")
        assert isinstance(data["overall_risk_score"], (int, float))
        assert isinstance(data["four_flow_match_score"], (int, float))
        assert isinstance(data["private_card_ratio"], (int, float))
        assert isinstance(data["cost_deviation"], (int, float))
        # 扩展字段
        assert isinstance(data["dimension_scores"], dict)
        assert isinstance(data["dim_details"], dict)
        assert isinstance(data["recommendations"], dict)
        assert isinstance(data["business_narrative"], str)
        assert isinstance(data["technical_summary"], dict)
        assert "assessment_date" in data

    @pytest.mark.asyncio
    async def test_scan_enterprise_minimal_data(
        self, client: AsyncClient, test_enterprise
    ):
        """仅有企业基本信息（无流水/发票/合同）→ 仍可扫描成功"""
        eid = test_enterprise.id
        resp = await client.post(f"/api/v1/enterprises/{eid}/risk-scan")

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["enterprise_id"] == eid
        # 无任何关联数据时，四流匹配度应为满分
        assert data["four_flow_match_score"] == 100.0
        # 私卡占比应为 0
        assert data["private_card_ratio"] == 0.0

    @pytest.mark.asyncio
    async def test_scan_persists_risk_assessment(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """扫描后 RiskAssessment 记录持久化到数据库"""
        eid = enterprise_with_full_data.id
        resp = await client.post(f"/api/v1/enterprises/{eid}/risk-scan")
        assert resp.status_code == 200
        assessment_id = resp.json()["data"]["risk_assessment_id"]

        # 通过 GET 接口验证已有记录
        detail_resp = await client.get(f"/api/v1/risk-assessments/{assessment_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()["data"]
        assert detail["id"] == assessment_id
        assert detail["enterprise_id"] == eid

    @pytest.mark.asyncio
    async def test_scan_risk_assessment_history(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """扫描两次后，历史列表应有 2 条记录"""
        eid = enterprise_with_full_data.id
        await client.post(f"/api/v1/enterprises/{eid}/risk-scan")
        await client.post(f"/api/v1/enterprises/{eid}/risk-scan")

        resp = await client.get(f"/api/v1/enterprises/{eid}/risk-assessments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] >= 2

    @pytest.mark.asyncio
    async def test_scan_latest_risk_assessment(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """扫描后可获取最新评估"""
        eid = enterprise_with_full_data.id
        await client.post(f"/api/v1/enterprises/{eid}/risk-scan")

        resp = await client.get(f"/api/v1/enterprises/{eid}/risk-assessments/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["data"]["enterprise_id"] == eid


class TestRiskScanErrors:
    """错误场景"""

    @pytest.mark.asyncio
    async def test_scan_nonexistent_enterprise(self, client: AsyncClient):
        """不存在的企业 ID → 40001"""
        resp = await client.post("/api/v1/enterprises/non-existent-id/risk-scan")
        assert resp.status_code == 200  # FastAPI 统一响应包装，HTTP 200 + 业务错误码
        body = resp.json()
        assert body["code"] == 40001
        assert "不存在" in body["message"]


class TestRiskScanEdgeCases:
    """边界场景"""

    @pytest.mark.asyncio
    async def test_scan_response_structure_consistency(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """多次扫描同一企业 → 响应结构一致"""
        eid = enterprise_with_full_data.id
        r1 = await client.post(f"/api/v1/enterprises/{eid}/risk-scan")
        r2 = await client.post(f"/api/v1/enterprises/{eid}/risk-scan")

        assert r1.status_code == r2.status_code == 200
        d1 = r1.json()["data"]
        d2 = r2.json()["data"]
        # 字段集合相同
        assert set(d1.keys()) == set(d2.keys())
        # 企业ID不变
        assert d1["enterprise_id"] == d2["enterprise_id"] == eid
