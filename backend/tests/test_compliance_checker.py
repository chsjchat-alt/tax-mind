"""
compliance_checker.run_compliance_check 单元测试

覆盖 10 类合规规则的触发/不触发分支：
  1. vat_burden_zero / vat_burden_low（high 与 medium 两级严重度）
  2. income_tax_burden_low
  3. ar_spike / ap_spike / inventory_abnormal
  4. current_ratio_abnormal / asset_liability_ratio_high
  5. depreciation_insufficient（含"折旧"关键字匹配与 /2 估算回退）
  6. declared_rev_gap（正负差异）
  7. four_flow_mismatch（仅传四流数据时触发）与数据缺失跳过
  8. 未知行业回退"批发零售"基准、行业阈值差异
"""

from app.core.compliance_checker import (
    run_compliance_check,
    ComplianceFinding,
    INDUSTRY_TAX_BURDEN_ALERTS,
    INDUSTRY_BENCHMARKS,
)
from app.core.four_flow_match import (
    ContractRecord,
    InvoiceRecord,
    BankTransactionRecord,
)
from datetime import date
from decimal import Decimal


def _deep_merge(base, override):
    """递归合并嵌套 dict，供 _base 覆盖局部字段"""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _base(**overrides):
    """构造合规基线输入（批发零售、月营收 10 万，无任何触发条件）"""
    data = {
        "enterprise_name": "测试企业",
        "industry": "批发零售",
        "annual_revenue": 1200000,
        "vouchers": [],
        "trial_balance": {
            "opening_balance": {"1601": 500000},
            "closing_balance": {"1122": 10000, "2202": -10000, "1405": 10000},
        },
        "financial_statements": {
            "balance_sheet": {
                "total_assets": 500000,
                "total_liabilities": 200000,
                "items": {"流动资产": 60000, "流动负债": 50000},
            },
            "income_statement": {"items": {"一、营业收入": 100000}},
        },
        "tax_ledger": {
            "vat": {
                "net_payable": 2000,
                "output_tax": 10000,
                "input_tax": 8000,
                "declared_revenue": 0,
            },
            "corporate_income_tax": {"tax_payable": 500},
        },
    }
    return _deep_merge(data, overrides)


def _keys(findings):
    return {f["rule_key"] for f in findings}


def _find(findings, rule_key):
    return next(f for f in findings if f["rule_key"] == rule_key)


# ═══════════════════════════════════════════
# 合规基线（无任何发现）
# ═══════════════════════════════════════════

def test_baseline_no_findings():
    """合规基线输入不应产生任何发现"""
    findings = run_compliance_check(**_base())
    assert findings == []


# ═══════════════════════════════════════════
# 增值税税负率
# ═══════════════════════════════════════════

def test_vat_burden_zero_triggered():
    """应纳税额 0 且月营收 >10000 → vat_burden_zero"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"net_payable": 0, "input_tax": 10000}},
    ))
    f = _find(findings, "vat_burden_zero")
    assert f["severity"] == "high"
    assert f["metrics"]["vat_burden_pct"] == 0


def test_vat_burden_low_high_severity():
    """税负率低于行业 critical 值 → high 级 vat_burden_low"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"net_payable": 500}},  # 0.5% < 批发零售 vat_critical 0.8
    ))
    f = _find(findings, "vat_burden_low")
    assert f["severity"] == "high"
    assert f["metrics"]["warning_threshold"] == INDUSTRY_TAX_BURDEN_ALERTS["批发零售"]["vat_critical"]


def test_vat_burden_low_medium_severity():
    """税负率低于行业 warning 值但高于 critical → medium 级 vat_burden_low"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"net_payable": 1000}},  # 1.0% < 批发零售 vat_warning 1.5
    ))
    f = _find(findings, "vat_burden_low")
    assert f["severity"] == "medium"
    assert f["metrics"]["warning_threshold"] == INDUSTRY_TAX_BURDEN_ALERTS["批发零售"]["vat_warning"]


def test_vat_burden_normal_no_finding():
    """税负率高于预警值 → 无增值税发现"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"net_payable": 3000}},  # 3.0% > 1.5
    ))
    assert "vat_burden_zero" not in _keys(findings)
    assert "vat_burden_low" not in _keys(findings)


# ═══════════════════════════════════════════
# 企业所得税贡献率
# ═══════════════════════════════════════════

def test_income_tax_burden_low():
    """企业所得税贡献率低于行业下限 → income_tax_burden_low"""
    findings = run_compliance_check(**_base(
        tax_ledger={"corporate_income_tax": {"tax_payable": 100}},  # 0.1% < 0.5
    ))
    f = _find(findings, "income_tax_burden_low")
    assert f["severity"] == "medium"
    assert f["metrics"]["cit_burden_pct"] == 0.1


def test_income_tax_normal_no_finding():
    findings = run_compliance_check(**_base(
        tax_ledger={"corporate_income_tax": {"tax_payable": 1000}},  # 1.0% ≥ 0.5
    ))
    assert "income_tax_burden_low" not in _keys(findings)


# ═══════════════════════════════════════════
# 应收 / 应付 / 存货
# ═══════════════════════════════════════════

def test_ar_spike():
    """应收账款周转天数超行业上限 → ar_spike"""
    findings = run_compliance_check(**_base(
        trial_balance={"closing_balance": {"1122": 1000000}},  # 周转天数 300 > 90
    ))
    f = _find(findings, "ar_spike")
    assert f["severity"] == "medium"
    assert f["metrics"]["ar_days"] == 300


def test_ap_spike():
    """应付账款周转天数超上限且余额>10000 → ap_spike"""
    findings = run_compliance_check(**_base(
        trial_balance={"closing_balance": {"2202": -1000000}},
    ))
    f = _find(findings, "ap_spike")
    assert f["severity"] == "low"
    assert f["metrics"]["ap_balance"] == 1000000


def test_ap_small_balance_no_finding():
    """应付余额 ≤10000 即使周转天数高也不触发"""
    findings = run_compliance_check(**_base(
        trial_balance={"closing_balance": {"2202": -10000}},
    ))
    assert "ap_spike" not in _keys(findings)


def test_inventory_abnormal():
    """存货周转天数超上限且余额>10000 → inventory_abnormal"""
    findings = run_compliance_check(**_base(
        trial_balance={"closing_balance": {"1405": 1000000}},  # 429 天 > 100
    ))
    f = _find(findings, "inventory_abnormal")
    assert f["severity"] == "medium"
    assert f["metrics"]["inv_days"] == 429


# ═══════════════════════════════════════════
# 财务比率
# ═══════════════════════════════════════════

def test_current_ratio_abnormal():
    """流动比率低于安全线 → current_ratio_abnormal"""
    findings = run_compliance_check(**_base(
        financial_statements={"balance_sheet": {"items": {
            "流动资产": 50000, "流动负债": 100000,  # 0.5 < 1.0
        }}},
    ))
    f = _find(findings, "current_ratio_abnormal")
    assert f["severity"] == "low"
    assert f["metrics"]["current_ratio"] == 0.5


def test_asset_liability_ratio_high():
    """资产负债率超行业上限 → asset_liability_ratio_high"""
    findings = run_compliance_check(**_base(
        financial_statements={"balance_sheet": {
            "total_assets": 100000, "total_liabilities": 90000,  # 90% > 70%
        }},
    ))
    f = _find(findings, "asset_liability_ratio_high")
    assert f["severity"] == "medium"
    assert f["metrics"]["asset_liability_ratio"] == 90.0


# ═══════════════════════════════════════════
# 折旧计提
# ═══════════════════════════════════════════

def _dep_voucher(amount, description="计提折旧"):
    return {
        "description": description,
        "entries": [{"account_code": "1602", "amount": amount}],
    }


def test_depreciation_insufficient():
    """实际折旧 < 测算基准 60% → depreciation_insufficient"""
    findings = run_compliance_check(**_base(
        trial_balance={"opening_balance": {"1601": 1000000}},  # expected_dep = 8000
        vouchers=[_dep_voucher(1000)],
    ))
    f = _find(findings, "depreciation_insufficient")
    assert f["severity"] == "low"
    assert f["metrics"]["expected_dep"] == 8000.0
    assert f["metrics"]["actual_dep"] == 1000.0


def test_depreciation_fallback_estimate():
    """凭证描述不含'折旧'时按 /2 估算折旧额"""
    findings = run_compliance_check(**_base(
        trial_balance={"opening_balance": {"1601": 1000000}},
        vouchers=[_dep_voucher(2000, description="结转成本")],
    ))
    f = _find(findings, "depreciation_insufficient")
    assert f["metrics"]["actual_dep"] == 1000.0  # 2000/2


def test_depreciation_sufficient_no_finding():
    """实际折旧充足 → 不触发折旧规则"""
    findings = run_compliance_check(**_base(
        trial_balance={"opening_balance": {"1601": 1000000}},  # expected 8000
        vouchers=[_dep_voucher(8000)],
    ))
    assert "depreciation_insufficient" not in _keys(findings)


# ═══════════════════════════════════════════
# 申报收入差异
# ═══════════════════════════════════════════

def test_declared_rev_gap_positive():
    """申报收入高于账面 20% → declared_rev_gap"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"declared_revenue": 120000}},
    ))
    f = _find(findings, "declared_rev_gap")
    assert f["severity"] == "high"
    assert f["metrics"]["gap_pct"] == 20.0


def test_declared_rev_gap_negative():
    """申报收入低于账面 50% → 同样触发"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"declared_revenue": 50000}},
    ))
    f = _find(findings, "declared_rev_gap")
    assert f["metrics"]["gap_pct"] == -50.0


def test_declared_rev_gap_within_threshold():
    """差异 ≤5% → 不触发"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"declared_revenue": 104000}},  # +4%
    ))
    assert "declared_rev_gap" not in _keys(findings)


# ═══════════════════════════════════════════
# 四流匹配
# ═══════════════════════════════════════════

def test_four_flow_skipped_without_data():
    """未传合同/发票/流水 → 跳过四流检查，不产生发现"""
    findings = run_compliance_check(**_base())
    assert "four_flow_mismatch" not in _keys(findings)


def test_four_flow_mismatch_triggered():
    """四流完全不一致（match_rate=0）→ four_flow_mismatch"""
    contracts = [ContractRecord(
        contract_no="HT001", counterparty="甲客户",
        amount=Decimal("1000"), signing_date=date(2026, 1, 1),
    )]
    invoices = [InvoiceRecord(
        invoice_no="FP001", invoice_type="output", amount=Decimal("1000"),
        total_amount=Decimal("1000"), buyer_name="乙公司",
        seller_name="测试公司", product_name="商品A",
    )]
    bank_transactions = [BankTransactionRecord(
        transaction_date=date(2026, 1, 1), amount=Decimal("1000"),
        direction="inflow", account_type="corporate", counterparty="丙公司",
        description="", is_declared=True,
    )]
    findings = run_compliance_check(**_base(
        contracts=contracts, invoices=invoices, bank_transactions=bank_transactions,
    ))
    f = _find(findings, "four_flow_mismatch")
    assert f["severity"] == "high"
    assert f["metrics"]["flow_match_rate"] == 0.0
    assert f["metrics"]["match_count"] == 0


def test_four_flow_match_high_no_finding():
    """四流一致（match_rate=100）→ 不产生 four_flow_mismatch"""
    contracts = [ContractRecord(
        contract_no="HT001", counterparty="甲客户",
        amount=Decimal("1000"), signing_date=date(2026, 1, 1),
    )]
    invoices = [InvoiceRecord(
        invoice_no="FP001", invoice_type="output", amount=Decimal("1000"),
        total_amount=Decimal("1000"), buyer_name="甲客户",
        seller_name="测试公司", product_name="商品A",
    )]
    bank_transactions = [BankTransactionRecord(
        transaction_date=date(2026, 1, 1), amount=Decimal("1000"),
        direction="inflow", account_type="corporate", counterparty="甲客户",
        description="", is_declared=True,
    )]
    findings = run_compliance_check(**_base(
        contracts=contracts, invoices=invoices, bank_transactions=bank_transactions,
    ))
    assert "four_flow_mismatch" not in _keys(findings)


# ═══════════════════════════════════════════
# 行业阈值与输出结构
# ═══════════════════════════════════════════

def test_unknown_industry_falls_back_to_default():
    """未知行业回退'批发零售'阈值"""
    findings = run_compliance_check(**_base(
        industry="未知行业",
        tax_ledger={"vat": {"net_payable": 1000}},  # 1.0%：批发零售 warning=1.5 → 触发
    ))
    f = _find(findings, "vat_burden_low")
    assert f["severity"] == "medium"


def test_manufacturing_industry_threshold_differs():
    """制造行业 vat_critical=1.0：税负率 0.5% 触发 high 级"""
    findings = run_compliance_check(**_base(
        industry="制造",
        tax_ledger={"vat": {"net_payable": 500}},  # 0.5% < 制造 vat_critical 1.0
    ))
    f = _find(findings, "vat_burden_low")
    assert f["severity"] == "high"
    assert INDUSTRY_BENCHMARKS["制造"]["ar_days_max"] == 120


def test_finding_dict_structure():
    """发现条目必须包含完整结构化字段"""
    findings = run_compliance_check(**_base(
        tax_ledger={"vat": {"net_payable": 0, "input_tax": 10000}},
    ))
    for f in findings:
        assert set(f.keys()) == {
            "rule_key", "category", "severity", "title",
            "description", "suggestion", "metrics",
        }
    assert any(f["rule_key"] == "vat_burden_zero" for f in findings)


def test_compliance_finding_to_dict():
    """ComplianceFinding.to_dict 输出字段完整性"""
    finding = ComplianceFinding(
        rule_key="test_rule", category="tax", severity="medium",
        title="t", description="d", suggestion="s", metrics={"a": 1},
    )
    d = finding.to_dict()
    assert d["rule_key"] == "test_rule"
    assert d["metrics"] == {"a": 1}
    empty = ComplianceFinding("r", "c", "low", "t", "d", "s")
    assert empty.to_dict()["metrics"] == {}
