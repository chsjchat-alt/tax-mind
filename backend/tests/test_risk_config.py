"""B1 参数配置化测试：risk_config 服务 + 引擎读配置（确定性，不依赖真实 DB）"""
import pytest
from decimal import Decimal

from app.core.risk_config import (
    DEFAULT_RISK_CONFIG, get_risk_config, upsert_risk_config,
)
from app.core.risk_engine import (
    assess_enterprise_risk, EnterpriseRiskInput,
)
from app.core.penalty_calculator import (
    calculate_compound_penalty_exposure, _calculate_iit_hidden_dividend,
    UnpaidTaxInput,
)
from app.core.tax_risk_engine import (
    calculate_comprehensive_tax_risk, EnterpriseDataPayload,
)
from app.models.risk_config import RiskConfig


# ═══════════════════════════════════════════════════════
# Fake DB（最小化：execute → scalars → all / scalar_one_or_none）
# ═══════════════════════════════════════════════════════

class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, rows=None, exc=None):
        self._rows = rows or []
        self._exc = exc
        self.committed = False
        self.added = []

    async def execute(self, *_args, **_kwargs):
        if self._exc is not None:
            raise self._exc
        return _FakeResult(self._rows)

    async def commit(self):
        self.committed = True

    def add(self, obj):
        self.added.append(obj)


# ═══════════════════════════════════════════════════════
# 配置服务
# ═══════════════════════════════════════════════════════

class TestRiskConfigService:
    def test_defaults_cover_w_s_p_c_r_q_params(self):
        """默认配置覆盖 W/S/P/C/R/Q 全部参数组"""
        required_keys = {
            # 阈值
            "risk_high_threshold", "risk_medium_threshold",
            "risk_critical_threshold", "risk_high_level_threshold",
            "risk_medium_high_threshold", "risk_medium_level_threshold",
            "high_dimension_score_threshold",
            # W 权重
            "weights_7dim", "weights_5dim",
            # S 严重度倍数
            "penalty_multiplier", "ghost_invoice_multiplier",
            "late_fee_daily_rate", "iit_dividend_rate",
            # R 修复加分
            "reduction_pct_per_task", "reduction_pct_max",
            # Q 法定信用扣分
            "credit_deduction_items",
        }
        assert required_keys <= set(DEFAULT_RISK_CONFIG)
        # 每个参数必须标注权威来源（多源互证要求）
        for key, meta in DEFAULT_RISK_CONFIG.items():
            assert meta["value"] is not None, key
            assert meta.get("source"), f"{key} 缺少权威来源"

    def test_defaults_match_engine_constants(self):
        """默认权重/倍数与引擎既有硬编码一致（保证未配置时行为不变）"""
        assert DEFAULT_RISK_CONFIG["risk_high_threshold"]["value"] == 70.0
        assert DEFAULT_RISK_CONFIG["risk_medium_threshold"]["value"] == 40.0
        assert DEFAULT_RISK_CONFIG["penalty_multiplier"]["value"]["low"] == 0.5
        assert DEFAULT_RISK_CONFIG["penalty_multiplier"]["value"]["critical"] == 5.0
        assert DEFAULT_RISK_CONFIG["late_fee_daily_rate"]["value"] == 0.0005
        assert DEFAULT_RISK_CONFIG["iit_dividend_rate"]["value"] == 0.20
        assert DEFAULT_RISK_CONFIG["reduction_pct_per_task"]["value"] == 0.15
        assert DEFAULT_RISK_CONFIG["reduction_pct_max"]["value"] == 0.80

    @pytest.mark.asyncio
    async def test_get_returns_defaults_on_empty_table(self):
        db = _FakeDB(rows=[])
        config = await get_risk_config(db)
        assert config["risk_high_threshold"] == 70.0
        assert config["reduction_pct_max"] == 0.80

    @pytest.mark.asyncio
    async def test_get_merges_db_overrides(self):
        row = RiskConfig(config_key="risk_high_threshold", config_value=55.0)
        config = await get_risk_config(_FakeDB(rows=[row]))
        assert config["risk_high_threshold"] == 55.0
        # 未覆盖的键仍为默认值
        assert config["risk_medium_threshold"] == 40.0

    @pytest.mark.asyncio
    async def test_get_falls_back_on_db_error(self):
        config = await get_risk_config(_FakeDB(exc=RuntimeError("boom")))
        assert config["risk_high_threshold"] == 70.0
        assert config["credit_deduction_items"][0]["deduction"] == 5.0

    @pytest.mark.asyncio
    async def test_upsert_ignores_unknown_keys(self):
        db = _FakeDB(rows=[])
        applied = await upsert_risk_config(db, {"not_a_real_key": 1})
        assert applied == {}
        assert db.committed is True

    @pytest.mark.asyncio
    async def test_upsert_inserts_new_row(self):
        db = _FakeDB(rows=[])
        applied = await upsert_risk_config(
            db, {"risk_high_threshold": 66.0}, updated_by="u-1"
        )
        assert applied == {"risk_high_threshold": 66.0}
        assert len(db.added) == 1
        assert db.added[0].config_value == 66.0
        assert db.added[0].source  # 权威来源随新行写入

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_row(self):
        row = RiskConfig(config_key="risk_high_threshold", config_value=70.0)
        db = _FakeDB(rows=[row])
        await upsert_risk_config(db, {"risk_high_threshold": 55.0})
        assert row.config_value == 55.0


# ═══════════════════════════════════════════════════════
# 引擎读配置
# ═══════════════════════════════════════════════════════

class TestEnginesReadConfig:
    def _basic_input(self) -> EnterpriseRiskInput:
        return EnterpriseRiskInput(
            enterprise_name="配置测试企业",
            industry="制造",
            revenue_annual=Decimal("5000000.00"),
            tax_rate_industry=Decimal("3.0"),
            cost_rate_industry=Decimal("85.0"),
            actual_tax_burden_rate=Decimal("2.8"),
            actual_cost_rate=Decimal("84.0"),
            total_private_card_amount=Decimal("0"),
            total_revenue=Decimal("5000000.00"),
            total_input_invoice=Decimal("500000.00"),
            total_output_invoice=Decimal("650000.00"),
        )

    def _risky_input(self) -> EnterpriseRiskInput:
        """私卡占比 30%（行业锚点 8%）→ 单维度风险 72.5，综合约 14.5"""
        return EnterpriseRiskInput(
            enterprise_name="配置测试企业",
            industry="制造",
            revenue_annual=Decimal("5000000.00"),
            tax_rate_industry=Decimal("3.0"),
            cost_rate_industry=Decimal("85.0"),
            actual_tax_burden_rate=Decimal("2.8"),
            actual_cost_rate=Decimal("84.0"),
            total_private_card_amount=Decimal("1500000"),
            total_revenue=Decimal("5000000.00"),
            total_input_invoice=Decimal("500000.00"),
            total_output_invoice=Decimal("650000.00"),
        )

    def test_old_engine_defaults_when_config_none(self):
        """config=None → 阈值保持默认 70/40"""
        result = assess_enterprise_risk(self._basic_input())
        assert result.technical_summary["thresholds"] == {"high": 70, "medium": 40}

    def test_old_engine_reads_thresholds_from_config(self):
        """config 覆盖阈值 → 判定与 technical_summary 同步"""
        result = assess_enterprise_risk(
            self._risky_input(), config={
                "risk_high_threshold": 5.0,
                "risk_medium_threshold": 0.0,
                "high_dimension_score_threshold": 70.0,
            }
        )
        # 私卡维度 72.5 ≥ 70 → high_count=1 → 至少 medium；综合 14.5 ≥ 5 → high
        assert result.overall_risk_score >= 5.0
        assert result.overall_risk_level == "high"
        assert result.technical_summary["thresholds"]["high"] == 5.0

    def test_old_engine_reads_weights_from_config(self):
        """config 覆盖权重 → 综合分 = 四流维度风险分（其余权重为 0）"""
        from app.core.four_flow_match import FourFlowMatchResult
        poor = FourFlowMatchResult()
        poor.overall_score = 25.0
        result = assess_enterprise_risk(
            self._basic_input(),
            flow_match_result=poor,
            config={
                "weights_7dim": {
                    "four_flow_match": 1.0, "private_card_ratio": 0.0,
                    "large_personal_transfer": 0.0, "cost_deviation": 0.0,
                    "tax_burden_deviation": 0.0, "invoice_bank_mismatch": 0.0,
                    "input_output_imbalance": 0.0,
                },
            }
        )
        assert result.overall_risk_score == round(75.0, 2)

    def test_penalty_calculator_optional_params(self):
        """配置化倍数/税率注入 → 计算使用配置值"""
        result = calculate_compound_penalty_exposure(
            UnpaidTaxInput(
                unpaid_vat=Decimal("10000"), late_days=30, risk_level="high",
            ),
            penalty_multiplier={"high": Decimal("4.0")},
            late_fee_daily_rate=Decimal("0.001"),
        )
        assert result.penalty_multiplier == Decimal("4.0")
        assert result.admin_penalty == Decimal("40000.00")
        assert result.late_fee_total == Decimal("300.00")  # 10000 * 0.001 * 30

    def test_iit_rate_optional_param(self):
        """iit_rate 注入 → 穿透税额按配置税率"""
        unpaid = _calculate_iit_hidden_dividend(
            Decimal("100000"), 400, iit_rate=Decimal("0.25")
        )
        assert unpaid == Decimal("25000.00")

    @pytest.mark.asyncio
    async def test_five_dim_engine_reads_config(self):
        """五维引擎注入 config → 权重与阈值生效（不查 DB）"""
        payload = EnterpriseDataPayload(
            enterprise_id="ent-1", enterprise_name="配置测试",
            revenue_annual=Decimal("10000000"),
            total_cost=Decimal("6000000"), total_expenses=Decimal("1000000"),
            net_profit=Decimal("3000000"), total_assets=Decimal("5000000"),
            asset_type="heavy_asset", depreciation_amount=Decimal("50000"),
            depreciation_to_revenue_ratio=Decimal("0.01"),
            max_cost_expense_ratio=Decimal("0.70"),
            output_invoice_total=Decimal("1000000"),
            input_invoice_total=Decimal("800000"),
            declared_tax=Decimal("200000"), actual_paid=Decimal("180000"),
        )
        config = {
            "weights_5dim": {
                "macro_internal_control": 1.0, "vat_gaar": 0.0,
                "iit_hidden_dividend": 0.0, "compound_penalty": 0.0,
                "four_flow_match": 0.0,
            },
            "risk_critical_threshold": 0.5,  # 任意非零分即可判 critical
            "risk_high_level_threshold": 0.4,
            "risk_medium_high_threshold": 0.3,
            "risk_medium_level_threshold": 0.2,
        }
        result = await calculate_comprehensive_tax_risk(
            "ent-1", payload, _FakeDB(), config=config
        )
        # 干净载荷下 macro 维度 0 分 → 综合 0 分 → 落在 low（阈值 0.2 以下）
        assert result.overall_risk_score == 0.0
        assert result.overall_risk_level == "low"
        assert result.technical_summary["thresholds"]["critical"] == 0.5

    @pytest.mark.asyncio
    async def test_five_dim_engine_config_load_falls_back(self):
        """config=None + DB 不可用 → 回退默认阈值（不崩溃）"""
        result = await calculate_comprehensive_tax_risk(
            "ent-1", _payload(), _FakeDB(exc=RuntimeError("no table"))
        )
        assert 0.0 <= result.overall_risk_score <= 100.0
        assert result.technical_summary["thresholds"]["critical"] == 80


def _payload() -> EnterpriseDataPayload:
    return EnterpriseDataPayload(
        enterprise_id="ent-1", enterprise_name="测试",
        revenue_annual=Decimal("10000000"),
        total_cost=Decimal("6000000"), total_expenses=Decimal("1000000"),
        net_profit=Decimal("3000000"), total_assets=Decimal("5000000"),
        asset_type="heavy_asset", depreciation_amount=Decimal("50000"),
        depreciation_to_revenue_ratio=Decimal("0.01"),
        max_cost_expense_ratio=Decimal("0.70"),
        output_invoice_total=Decimal("1000000"),
        input_invoice_total=Decimal("800000"),
        declared_tax=Decimal("200000"), actual_paid=Decimal("180000"),
    )
