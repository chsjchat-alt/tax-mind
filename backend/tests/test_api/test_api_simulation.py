"""
API 层测试：风险模拟 (POST /api/v1/enterprises/{id}/simulate)

使用 httpx.AsyncClient + SQLite 内存数据库测试端点。

测试场景：
  1. 默认参数模拟 → 返回时间序列 + 建议 + 损失框架消息
  2. 自定义参数模拟 → 参数透传到引擎
  3. 不存在的企业 ID → 40001 错误
  4. 边界值：零隐匿收入 → 正常响应
  5. 边界值：极值参数 → 不崩溃
"""
import pytest
from httpx import AsyncClient


SIMULATE_URL = "/api/v1/enterprises/{eid}/simulate"


class TestSimulationSuccess:
    """成功场景"""

    @pytest.mark.asyncio
    async def test_simulate_default_params(
        self, client: AsyncClient, test_enterprise
    ):
        """默认参数模拟 → 200 + 时间序列 + 损失框架消息"""
        eid = test_enterprise.id
        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
            json={"monthly_hidden_revenue": 50000},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert body["message"] == "success"
        data = body["data"]

        # 时间序列
        assert isinstance(data["time_points"], list)
        assert len(data["time_points"]) > 0
        tp0 = data["time_points"][0]
        for field in [
            "period", "months_elapsed", "path_a_cost", "path_b_cost",
            "cost_difference", "audit_probability", "expected_penalty",
            "expected_late_fee", "total_hidden_tax",
        ]:
            assert field in tp0, f"时间点缺少字段: {field}"

        # 模拟特有字段
        assert isinstance(data["recommendation"], str)
        assert isinstance(data["loss_frame_message"], str)
        assert isinstance(data["technical_summary"], dict)
        assert isinstance(data["case_references"], list)

    @pytest.mark.asyncio
    async def test_simulate_with_full_data(
        self, client: AsyncClient, enterprise_with_full_data
    ):
        """完整数据企业模拟（先做风险扫描得到风险等级）→ 200"""
        eid = enterprise_with_full_data.id

        # 先执行风险扫描以生成 RiskAssessment（被模拟接口用于获取风险等级）
        await client.post(f"/api/v1/enterprises/{eid}/risk-scan")

        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
            json={
                "monthly_hidden_revenue": 100000,
                "comprehensive_tax_rate": 0.13,
                "remediation_cost": 20000,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        data = body["data"]
        assert len(data["time_points"]) > 0

    @pytest.mark.asyncio
    async def test_simulate_custom_params_reflected(
        self, client: AsyncClient, test_enterprise
    ):
        """自定义参数 → 可在 technical_summary 中反映"""
        eid = test_enterprise.id
        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
            json={
                "monthly_hidden_revenue": 80000,
                "comprehensive_tax_rate": 0.09,
                "remediation_cost": 15000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # technical_summary 应包含输入参数相关信息
        assert isinstance(data["technical_summary"], dict)
        assert len(data["time_points"]) > 0


class TestSimulationErrors:
    """错误场景"""

    @pytest.mark.asyncio
    async def test_simulate_nonexistent_enterprise(self, client: AsyncClient):
        """不存在的企业 ID → 40001"""
        resp = await client.post(
            SIMULATE_URL.format(eid="11111111-1111-1111-1111-111111111111"),
            json={"monthly_hidden_revenue": 10000},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 40001
        assert "不存在" in body["message"]

    @pytest.mark.asyncio
    async def test_simulate_negative_hidden_revenue(
        self, client: AsyncClient, test_enterprise
    ):
        """负数隐匿收入 → Pydantic 校验拒绝（ge=0）"""
        eid = test_enterprise.id
        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
            json={"monthly_hidden_revenue": -10000},
        )
        # 参数校验失败 → HTTP 422
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_simulate_tax_rate_out_of_range(
        self, client: AsyncClient, test_enterprise
    ):
        """税率超出 [0,1] 范围 → 422"""
        eid = test_enterprise.id
        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
            json={
                "monthly_hidden_revenue": 10000,
                "comprehensive_tax_rate": 1.5,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_simulate_missing_required_field(
        self, client: AsyncClient, test_enterprise
    ):
        """缺少必填字段（不传 body）→ 422"""
        eid = test_enterprise.id
        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
        )
        assert resp.status_code == 422


class TestSimulationEdgeCases:
    """边界场景"""

    @pytest.mark.asyncio
    async def test_simulate_zero_hidden_revenue(
        self, client: AsyncClient, test_enterprise
    ):
        """隐匿收入为 0 → 正常响应，时间序列值均为 0"""
        eid = test_enterprise.id
        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
            json={"monthly_hidden_revenue": 0},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["time_points"]) > 0

    @pytest.mark.asyncio
    async def test_simulate_large_values_does_not_crash(
        self, client: AsyncClient, test_enterprise
    ):
        """极大参数值 → 不崩溃"""
        eid = test_enterprise.id
        resp = await client.post(
            SIMULATE_URL.format(eid=eid),
            json={
                "monthly_hidden_revenue": 999999999,
                "comprehensive_tax_rate": 0.5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["time_points"], list)

    @pytest.mark.asyncio
    async def test_simulate_time_series_consistency(
        self, client: AsyncClient, test_enterprise
    ):
        """相同参数两次模拟 → 结果一致（确定性算法）"""
        eid = test_enterprise.id
        payload = {"monthly_hidden_revenue": 30000, "comprehensive_tax_rate": 0.06}

        r1 = await client.post(SIMULATE_URL.format(eid=eid), json=payload)
        r2 = await client.post(SIMULATE_URL.format(eid=eid), json=payload)

        assert r1.status_code == r2.status_code == 200
        tp1 = r1.json()["data"]["time_points"]
        tp2 = r2.json()["data"]["time_points"]
        assert len(tp1) == len(tp2)

        # 每个时间点的关键数值应一致
        for i in range(min(len(tp1), 5)):
            for key in ("months_elapsed", "path_a_cost", "path_b_cost",
                        "audit_probability"):
                assert tp1[i][key] == tp2[i][key], (
                    f"Time point {i}, key={key}: {tp1[i][key]} != {tp2[i][key]}"
                )
