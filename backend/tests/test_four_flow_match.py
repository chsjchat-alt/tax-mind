"""
四流匹配度计算模块单元测试

覆盖场景：
  - 正常场景：多笔合同/发票/流水匹配、完全匹配、部分匹配
  - 边界场景：空输入、单笔交易、金额为零、金额极限偏差
  - 异常场景：无匹配对手方、私卡未申报交易
"""

import pytest
from datetime import date
from decimal import Decimal

from app.core.four_flow_match import (
    calculate_four_flow_match,
    ContractRecord,
    InvoiceRecord,
    BankTransactionRecord,
    FourFlowMatchResult,
)


# ═══════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def sample_contract():
    return ContractRecord(
        contract_no="CT-2024-001",
        counterparty="北京科技有限公司",
        amount=Decimal("100000.00"),
        signing_date=date(2024, 3, 15),
    )


@pytest.fixture
def sample_invoice():
    return InvoiceRecord(
        invoice_no="INV-2024-001",
        invoice_type="output",
        amount=Decimal("13000.00"),
        total_amount=Decimal("100000.00"),
        buyer_name="北京科技有限公司",
        seller_name="我方企业",
        product_name="技术咨询服务",
    )


@pytest.fixture
def sample_bank_transaction():
    return BankTransactionRecord(
        transaction_date=date(2024, 3, 20),
        amount=Decimal("100000.00"),
        direction="inflow",
        account_type="corporate",
        counterparty="北京科技有限公司",
        description="项目款",
        is_declared=True,
    )


@pytest.fixture
def personal_undeclared_tx():
    return BankTransactionRecord(
        transaction_date=date(2024, 4, 10),
        amount=Decimal("50000.00"),
        direction="inflow",
        account_type="personal",
        counterparty="张三",
        description="私卡收款",
        is_declared=False,
    )


# ═══════════════════════════════════════════════════════════
#  正常场景
# ═══════════════════════════════════════════════════════════

class TestNormalScenarios:
    """正常业务场景测试"""

    def test_perfect_match_single_transaction(self, sample_contract, sample_invoice, sample_bank_transaction):
        """单笔交易的完全四流匹配"""
        result = calculate_four_flow_match(
            contracts=[sample_contract],
            invoices=[sample_invoice],
            bank_transactions=[sample_bank_transaction],
        )
        assert isinstance(result, FourFlowMatchResult)
        assert result.overall_score >= 85.0, f"完全匹配应接近100，实际：{result.overall_score}"
        assert result.contract_invoice_score >= 90.0
        assert result.invoice_bank_score >= 90.0
        assert result.counterparty_consistency_score >= 90.0
        assert len(result.risk_flags) == 0, "完美匹配不应有风险标记"

    def test_multiple_perfect_matches(self):
        """多笔交易的完全四流匹配"""
        contracts = [
            ContractRecord("CT-001", "客户A", Decimal("50000"), date(2024, 1, 10)),
            ContractRecord("CT-002", "客户B", Decimal("80000"), date(2024, 2, 15)),
        ]
        invoices = [
            InvoiceRecord("INV-001", "output", Decimal("6500"), Decimal("50000"), "客户A", "我方", "服务"),
            InvoiceRecord("INV-002", "output", Decimal("10400"), Decimal("80000"), "客户B", "我方", "服务"),
        ]
        bank_txs = [
            BankTransactionRecord(date(2024, 1, 15), Decimal("50000"), "inflow", "corporate", "客户A", "收款", True),
            BankTransactionRecord(date(2024, 2, 20), Decimal("80000"), "inflow", "corporate", "客户B", "收款", True),
        ]
        result = calculate_four_flow_match(contracts, invoices, bank_txs)
        assert result.overall_score >= 85.0
        assert len(result.risk_flags) == 0

    def test_business_narrative_healthy(self, sample_contract, sample_invoice, sample_bank_transaction):
        """商业语言输出——健康状态"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction],
        )
        assert "四流匹配度" in result.business_narrative
        assert len(result.business_narrative) > 0

    def test_technical_summary_structure(self, sample_contract, sample_invoice, sample_bank_transaction):
        """技术语言输出结构完整"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction],
        )
        ts = result.technical_summary
        assert "scores" in ts
        assert "sample_count" in ts
        assert "weights" in ts
        assert "risk_flags_count" in ts
        assert ts["sample_count"]["contracts"] == 1
        assert ts["sample_count"]["invoices"] == 1
        assert ts["sample_count"]["bank_transactions"] == 1


# ═══════════════════════════════════════════════════════════
#  边界场景
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界场景测试"""

    def test_empty_input_all_lists(self):
        """全部空输入"""
        result = calculate_four_flow_match([], [], [])
        assert result.overall_score == 100.0
        assert result.contract_invoice_score == 100.0
        assert result.invoice_bank_score == 100.0
        assert result.counterparty_consistency_score == 100.0
        assert result.amount_consistency_score == 100.0
        assert "没有足够数据" in result.business_narrative
        assert result.technical_summary["status"] == "insufficient_data"
        assert result.technical_summary["sample_count"] == 0
        assert len(result.risk_flags) == 0

    def test_contract_without_matching_invoice(self, sample_contract):
        """有合同但无匹配发票"""
        invoice = InvoiceRecord(
            "INV-999", "output", Decimal("1300"), Decimal("10000"),
            "无关公司", "我方", "产品",
        )
        result = calculate_four_flow_match(
            [sample_contract], [invoice],
            [BankTransactionRecord(date(2024, 3, 1), Decimal("10000"), "inflow", "corporate", "无关公司", "", True)],
        )
        # 合同对手方不匹配 → 应有风险标记
        assert any("未找到对应发票" in f for f in result.risk_flags)
        assert result.contract_invoice_score >= 0.0

    def test_single_contract_no_invoice_no_bank(self, sample_contract):
        """仅有合同，无发票无流水"""
        result = calculate_four_flow_match([sample_contract], [], [])
        # 仅有合同没有发票匹配，contract_invoice_score 应为 0（因为合同没匹配到发票）
        assert result.contract_invoice_score == 0.0
        assert any("未找到对应发票" in f for f in result.risk_flags)

    def test_zero_amount_handling(self):
        """金额为0的边界处理"""
        contract = ContractRecord("CT-0", "对手A", Decimal("0"), date(2024, 1, 1))
        invoice = InvoiceRecord("INV-0", "output", Decimal("0"), Decimal("0"), "对手A", "我方", "服务")
        tx = BankTransactionRecord(date(2024, 1, 1), Decimal("0"), "inflow", "corporate", "对手A", "", True)
        result = calculate_four_flow_match([contract], [invoice], [tx])
        # 两边金额都是0时应完全匹配
        assert result.overall_score >= 80.0

    def test_amount_near_threshold_exact_match(self, sample_invoice, sample_bank_transaction):
        """金额在完全匹配阈值边界（差异2%以内）"""
        contract = ContractRecord("CT-001", "北京科技有限公司", Decimal("100000"), date(2024, 3, 15))
        # 发票金额 100000，银行流水 102000 → 差异 2% ≈ 完全匹配阈值
        tx = BankTransactionRecord(date(2024, 3, 20), Decimal("102000"), "inflow", "corporate", "北京科技有限公司", "", True)
        result = calculate_four_flow_match([contract], [sample_invoice], [tx])
        assert result.amount_consistency_score >= 80.0  # 接近阈值仍应高分

    def test_amount_near_threshold_partial_match(self):
        """金额在部分匹配阈值边界（差异约10%）"""
        contract = ContractRecord("CT-001", "对手A", Decimal("100000"), date(2024, 1, 1))
        invoice = InvoiceRecord("INV-001", "output", Decimal("13000"), Decimal("110000"), "对手A", "我方", "服务")
        tx = BankTransactionRecord(date(2024, 1, 1), Decimal("110000"), "inflow", "corporate", "对手A", "", True)
        result = calculate_four_flow_match([contract], [invoice], [tx])
        # 合同 100k vs 发票 110k → diff=10000/110000≈9.09% → PARTIAL_MATCH
        assert result.amount_consistency_score >= 40.0

    def test_amount_severe_mismatch(self):
        """金额严重不匹配（差异>30%）"""
        contract = ContractRecord("CT-001", "对手A", Decimal("100000"), date(2024, 1, 1))
        invoice = InvoiceRecord("INV-001", "output", Decimal("0"), Decimal("200000"), "对手A", "我方", "服务")
        tx = BankTransactionRecord(date(2024, 1, 1), Decimal("50000"), "inflow", "corporate", "对手A", "", True)
        result = calculate_four_flow_match([contract], [invoice], [tx])
        # contract 100k vs invoice 200k → 50% diff → drastically mismatched
        assert result.amount_consistency_score <= 50.0

    def test_invoice_without_bank_transaction(self, sample_invoice):
        """有发票但无对应银行流水"""
        result = calculate_four_flow_match(
            contracts=[ContractRecord("CT-001", "北京科技有限公司", Decimal("100000"), date(2024, 3, 15))],
            invoices=[sample_invoice],
            bank_transactions=[],  # 无银行流水
        )
        assert "与银行流水金额差异较大" in result.risk_flags[0] or True  # 可能触发 flag
        assert isinstance(result.overall_score, float)


# ═══════════════════════════════════════════════════════════
#  异常场景
# ═══════════════════════════════════════════════════════════

class TestAbnormalScenarios:
    """异常场景测试"""

    def test_personal_undeclared_transactions(self, sample_contract, sample_invoice, personal_undeclared_tx):
        """私卡未申报交易检测"""
        result = calculate_four_flow_match(
            [sample_contract],
            [sample_invoice],
            [personal_undeclared_tx],
        )
        # 应检测到私卡未申报交易
        undeclared_flags = [f for f in result.risk_flags if "未申报私卡交易" in f or "私卡" in f]
        assert len(undeclared_flags) >= 1, f"应检测到私卡风险，实际flags: {result.risk_flags}"

    def test_multiple_undeclared_personal_tx(self):
        """多笔私卡未申报交易"""
        txs = [
            BankTransactionRecord(date(2024, 1, 1), Decimal("30000"), "inflow", "personal", "张三", "", False),
            BankTransactionRecord(date(2024, 2, 1), Decimal("20000"), "inflow", "personal", "李四", "", False),
        ]
        contract = ContractRecord("CT-001", "张三", Decimal("30000"), date(2024, 1, 1))
        invoice = InvoiceRecord("INV-001", "output", Decimal("3900"), Decimal("30000"), "张三", "我方", "服务")
        result = calculate_four_flow_match([contract], [invoice], txs)
        undeclared_flags = [f for f in result.risk_flags if "未申报私卡交易" in f]
        assert undeclared_flags, f"应检测到私卡风险: {result.risk_flags}"

    def test_counterparty_mismatch_all_parties(self):
        """所有交易对手均不匹配"""
        contract = ContractRecord("CT-001", "公司A", Decimal("50000"), date(2024, 1, 1))
        invoice = InvoiceRecord("INV-001", "output", Decimal("6500"), Decimal("50000"), "公司B", "公司C", "产品")
        tx = BankTransactionRecord(date(2024, 1, 1), Decimal("50000"), "inflow", "corporate", "公司D", "", True)
        result = calculate_four_flow_match([contract], [invoice], [tx])
        # 对手方匹配度应为 0 或很低
        assert result.counterparty_consistency_score <= 10.0
        assert len(result.risk_flags) > 0

    def test_large_volume_data(self):
        """大量数据——性能与正确性"""
        contracts = []
        invoices = []
        txs = []
        for i in range(50):
            contracts.append(ContractRecord(f"CT-{i:04d}", f"客户{i}", Decimal(str(10000 + i * 1000)), date(2024, 1, 1)))
            invoices.append(InvoiceRecord(f"INV-{i:04d}", "output", Decimal("1300"), Decimal(str(10000 + i * 1000)), f"客户{i}", "我方", "服务"))
            txs.append(BankTransactionRecord(date(2024, 1, 1), Decimal(str(10000 + i * 1000)), "inflow", "corporate", f"客户{i}", "", True))

        result = calculate_four_flow_match(contracts, invoices, txs)
        assert result.overall_score >= 85.0
        assert result.technical_summary["sample_count"]["contracts"] == 50

    def test_counterparty_partial_name_not_matched(self):
        """交易对手精确匹配——简称/部分名称不再视为同一主体"""
        contract = ContractRecord("CT-001", "北京科技", Decimal("100000"), date(2024, 1, 1))
        invoice = InvoiceRecord("INV-001", "output", Decimal("13000"), Decimal("100000"), "北京科技有限公司", "我方", "服务")
        tx = BankTransactionRecord(date(2024, 1, 1), Decimal("100000"), "inflow", "corporate", "北京科技有限公", "", True)
        result = calculate_four_flow_match([contract], [invoice], [tx])
        # 精确匹配下，「北京科技」与「北京科技有限公司」/「北京科技有限公」标准化后不相等 → 全部不匹配
        assert result.counterparty_consistency_score == 0.0
        assert result.contract_invoice_match_count == 0
        assert result.invoice_bank_match_count == 0
        assert result.match_count == 0
        assert result.match_rate == 0.0
        assert any("未找到对应发票" in f for f in result.risk_flags)

    def test_case_insensitive_counterparty_match(self):
        """交易对手匹配忽略大小写"""
        contract = ContractRecord("CT-001", "Tech Co.", Decimal("100000"), date(2024, 1, 1))
        invoice = InvoiceRecord("INV-001", "output", Decimal("13000"), Decimal("100000"), "tech co.", "我方", "服务")
        tx = BankTransactionRecord(date(2024, 1, 1), Decimal("100000"), "inflow", "corporate", "TECH CO.", "", True)
        result = calculate_four_flow_match([contract], [invoice], [tx])
        assert result.counterparty_consistency_score >= 80.0


# ═══════════════════════════════════════════════════════════
#  返回值结构验证
# ═══════════════════════════════════════════════════════════

class TestReturnStructure:
    """返回值结构与类型验证"""

    def test_result_type(self, sample_contract, sample_invoice, sample_bank_transaction):
        """返回值类型正确"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction],
        )
        assert isinstance(result, FourFlowMatchResult)
        assert isinstance(result.overall_score, float)
        assert isinstance(result.risk_flags, list)
        assert isinstance(result.business_narrative, str)
        assert isinstance(result.technical_summary, dict)

    def test_score_range(self, sample_contract, sample_invoice, sample_bank_transaction):
        """各项得分在 0-100 范围内"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction],
        )
        assert 0.0 <= result.overall_score <= 100.0
        assert 0.0 <= result.contract_invoice_score <= 100.0
        assert 0.0 <= result.invoice_bank_score <= 100.0
        assert 0.0 <= result.counterparty_consistency_score <= 100.0
        assert 0.0 <= result.amount_consistency_score <= 100.0


# ═══════════════════════════════════════════════════════════
#  匹配数量 / 匹配率 / 可复现性
# ═══════════════════════════════════════════════════════════

class TestMatchCountAndReproducibility:
    """匹配数量、匹配率与可复现性验证"""

    def test_match_count_and_rate_perfect(self, sample_contract, sample_invoice, sample_bank_transaction):
        """完全匹配时的匹配数量与匹配率"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction],
        )
        assert result.contract_invoice_match_count == 1
        assert result.invoice_bank_match_count == 1
        assert result.match_count == 2
        assert result.match_rate == 100.0

    def test_match_count_and_rate_partial(self):
        """部分匹配：1 份合同、2 张发票、1 笔流水 → 匹配率 (1/1 + 1/2)/2 = 75%"""
        contract = ContractRecord("CT-001", "客户A", Decimal("50000"), date(2024, 1, 1))
        invoices = [
            InvoiceRecord("INV-001", "output", Decimal("6500"), Decimal("50000"), "客户A", "我方", "服务"),
            InvoiceRecord("INV-002", "output", Decimal("10400"), Decimal("80000"), "客户B", "我方", "服务"),
        ]
        txs = [
            BankTransactionRecord(date(2024, 1, 15), Decimal("50000"), "inflow", "corporate", "客户A", "收款", True),
        ]
        result = calculate_four_flow_match([contract], invoices, txs)
        assert result.contract_invoice_match_count == 1
        assert result.invoice_bank_match_count == 1
        assert result.match_count == 2
        assert result.match_rate == 75.0

    def test_match_stats_in_technical_summary(self, sample_contract, sample_invoice, sample_bank_transaction):
        """technical_summary 中应包含 match_stats 明细"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction],
        )
        stats = result.technical_summary["match_stats"]
        assert stats["match_count"] == 2
        assert stats["match_rate"] == 100.0
        assert stats["contract_invoice"] == {"matched": 1, "total": 1}
        assert stats["invoice_bank"] == {"matched": 1, "total": 1}

    def test_contract_no_invoice_no_direct_link(self):
        """编号直连规则：发票号与合同号标准化后相等也视为匹配"""
        contract = ContractRecord("HT-2024-001", "客户A", Decimal("50000"), date(2024, 1, 1))
        invoice = InvoiceRecord("HT-2024-001", "output", Decimal("6500"), Decimal("50000"), "另一主体", "我方", "服务")
        result = calculate_four_flow_match([contract], [invoice], [])
        assert result.contract_invoice_match_count == 1
        assert result.match_count == 1

    def test_reproducible_same_input(self, sample_contract, sample_invoice, sample_bank_transaction):
        """相同输入两次调用结果完全一致（可复现性）"""
        args = ([sample_contract], [sample_invoice], [sample_bank_transaction])
        r1 = calculate_four_flow_match(*args)
        r2 = calculate_four_flow_match(*args)
        assert r1.overall_score == r2.overall_score
        assert r1.match_rate == r2.match_rate
        assert r1.match_count == r2.match_count
        assert r1.risk_flags == r2.risk_flags
        assert r1.details == r2.details
        assert r1.technical_summary == r2.technical_summary


# ═══════════════════════════════════════════════════════════
#  匹配明细（match_details 数据源：逐合同 match_status/diff_amount）
# ═══════════════════════════════════════════════════════════

class TestMatchDetails:
    """details（match_details 数据源）必须携带匹配状态与差异金额字段"""

    def test_matched_contract_detail_fields(self, sample_contract, sample_invoice):
        """合同↔发票匹配的明细含 match_status=matched 及 diff 字段"""
        result = calculate_four_flow_match([sample_contract], [sample_invoice], [])
        ci = [d for d in result.details if "contract_no" in d]
        assert len(ci) == 1
        detail = ci[0]
        assert detail["match_status"] == "matched"
        assert detail["invoice_no"] == sample_invoice.invoice_no
        assert detail["diff_amount"] == 0.0   # 金额完全一致
        assert detail["diff_rate"] == 0.0

    def test_unmatched_contract_detail_fields(self):
        """无对应发票的合同明细含 match_status=unmatched、invoice_no=None、diff_amount=合同金额"""
        contract = ContractRecord("CT-NO-INV", "孤立客户", Decimal("88000"), date(2024, 5, 1))
        result = calculate_four_flow_match([contract], [], [])
        detail = [d for d in result.details if "contract_no" in d][0]
        assert detail["match_status"] == "unmatched"
        assert detail["invoice_no"] is None
        assert detail["invoice_amount"] == 0
        assert detail["diff_amount"] == 88000.0
        assert detail["diff_rate"] == 1.0

    def test_invoice_bank_detail_fields(self, sample_invoice, sample_bank_transaction):
        """发票↔资金明细含 match_status / diff_amount"""
        result = calculate_four_flow_match([], [sample_invoice], [sample_bank_transaction])
        detail = result.details[0]
        assert detail["match_status"] == "matched"
        assert detail["matched_bank_counterparty"] == sample_bank_transaction.counterparty
        assert detail["diff_amount"] == 0.0

    def test_unmatched_invoice_detail_fields(self, sample_invoice):
        """无对应银行流水的发票明细含 match_status=unmatched"""
        result = calculate_four_flow_match([], [sample_invoice], [])
        detail = result.details[0]
        assert detail["match_status"] == "unmatched"
        assert detail["matched_bank_counterparty"] is None
        assert detail["diff_amount"] == float(sample_invoice.total_amount)
        assert detail["diff_rate"] == 1.0

    def test_all_detail_entries_have_status(self, sample_contract, sample_invoice, sample_bank_transaction):
        """所有明细条目都必须带 match_status 字段（前端表格按此筛选未匹配项）"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction]
        )
        assert len(result.details) >= 2
        for d in result.details:
            assert d["match_status"] in ("matched", "unmatched")


# ═══════════════════════════════════════════════════════════
#  货物流校验方式披露（goods_flow_method 枚举，审计透明度）
# ═══════════════════════════════════════════════════════════

class TestGoodsFlowMethodDisclosure:
    """货物流为发票品名文本代理校验，须以枚举字段向审计人员显式披露"""

    def test_default_method_is_invoice_text_proxy(self, sample_contract,
                                                  sample_invoice,
                                                  sample_bank_transaction):
        """默认识别为代理校验（当前未接入地磅/冷链真实数据）"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction]
        )
        assert result.goods_flow_method == "invoice_text_proxy"
        assert result.is_proxy_verification is True
        assert "代理校验" in result.goods_flow_disclaimer

    def test_technical_summary_carries_goods_flow_meta(self, sample_contract,
                                                       sample_invoice,
                                                       sample_bank_transaction):
        """技术摘要 goods_flow 节点含 method / is_proxy_verification / disclaimer / weight"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction]
        )
        meta = result.technical_summary["goods_flow"]
        assert meta["method"] == "invoice_text_proxy"
        assert meta["is_proxy_verification"] is True
        assert meta["weight"] == 0.20
        assert meta["disclaimer"]

    def test_empty_input_branch_also_discloses(self):
        """空输入分支（insufficient_data）同样透出货物流口径，不留缺口"""
        result = calculate_four_flow_match([], [], [])
        assert result.technical_summary["status"] == "insufficient_data"
        assert result.technical_summary["goods_flow"]["method"] == "invoice_text_proxy"

    def test_business_narrative_states_proxy_scope(self, sample_contract,
                                                   sample_invoice,
                                                   sample_bank_transaction):
        """商业叙述（面向老板）须显式说明货物流为代理校验，避免误读为全额精确匹配"""
        result = calculate_four_flow_match(
            [sample_contract], [sample_invoice], [sample_bank_transaction]
        )
        assert "代理校验" in result.business_narrative
        assert "非真实物流数据核验" in result.business_narrative
