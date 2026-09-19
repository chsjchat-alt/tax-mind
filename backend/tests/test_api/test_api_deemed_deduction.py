"""核定扣除计算 API 测试（V4 §4.2 引擎的首个生产调用链路 + 证据链挂载）

口径：
  - 自动路由成功 → calc_id 非空、同输入重算 calc_id 一致（确定性，§3.2 验收）；
  - 任一步无法确定性完成 → route=manual 并给出原因，禁止默认套用（引擎铁律）；
  - 非法/非正数值 → 40001 拒绝（Decimal 精度入口守卫）。
"""
import pytest
import httpx


def _auto_payload(**overrides) -> dict:
    payload = {
        "entity_is_pilot": True,
        "product_kind": "uht",
        "animal": "cow",
        "high_protein": False,
        "sales_quantity": "100",
        "avg_purchase_price": "0.4",
        "product_name": "灭菌乳",
    }
    payload.update(overrides)
    return payload


class TestDeemedDeductionApi:
    @pytest.mark.asyncio
    async def test_auto_route_returns_calc_id_and_amount(
        self, client: httpx.AsyncClient,
    ):
        """试点主体 + 灭菌乳 → auto 路由：金额、calc_id、规则引用齐全"""
        resp = await client.post(
            "/api/v1/deemed-deduction/calculate", json=_auto_payload()
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["is_auto"] is True
        result = data["result"]
        assert result["route"] == "auto"
        assert result["calc_id"]
        assert result["input_vat"] == "3.53"   # Decimal 金额字符串（精确到分）
        assert result["rule_ids"]
        assert result["params_snapshot"]

    @pytest.mark.asyncio
    async def test_same_input_deterministic_calc_id(
        self, client: httpx.AsyncClient,
    ):
        """V4 §3.2 验收：相同输入参数重算 calc_id 一致率 100%"""
        r1 = await client.post(
            "/api/v1/deemed-deduction/calculate", json=_auto_payload()
        )
        r2 = await client.post(
            "/api/v1/deemed-deduction/calculate", json=_auto_payload()
        )
        assert (
            r1.json()["data"]["result"]["calc_id"]
            == r2.json()["data"]["result"]["calc_id"]
        )

    @pytest.mark.asyncio
    async def test_unknown_voucher_routes_to_manual(
        self, client: httpx.AsyncClient,
    ):
        """非试点 + 未知凭证类型 → manual（禁止默认套用），不产出 calc_id"""
        resp = await client.post(
            "/api/v1/deemed-deduction/calculate",
            json=_auto_payload(
                entity_is_pilot=False, voucher_type="bogus_voucher",
            ),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_auto"] is False
        result = data["result"]
        assert result["route"] == "manual"
        assert "转人工" in result["reason"]
        assert not result["calc_id"]
        assert result["input_vat"] is None

    @pytest.mark.asyncio
    async def test_missing_product_name_routes_to_manual(
        self, client: httpx.AsyncClient,
    ):
        """缺产品名称 → 『鲜奶』范围无法判定 → manual（不默认套用 9%）"""
        resp = await client.post(
            "/api/v1/deemed-deduction/calculate",
            json=_auto_payload(product_name=""),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_auto"] is False
        assert data["result"]["route"] == "manual"

    @pytest.mark.asyncio
    async def test_invalid_number_rejected(self, client: httpx.AsyncClient):
        """非数字字符串 → 40001"""
        resp = await client.post(
            "/api/v1/deemed-deduction/calculate",
            json=_auto_payload(sales_quantity="abc"),
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 40001

    @pytest.mark.asyncio
    async def test_non_positive_number_rejected(self, client: httpx.AsyncClient):
        """数量/单价必须为正 → 40001"""
        resp = await client.post(
            "/api/v1/deemed-deduction/calculate",
            json=_auto_payload(sales_quantity="-5"),
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 40001
        resp2 = await client.post(
            "/api/v1/deemed-deduction/calculate",
            json=_auto_payload(avg_purchase_price="0"),
        )
        assert resp2.json()["code"] == 40001
