"""
四流匹配度计算模块

「四流」是金税四期稽查的核心逻辑，指：
  - 合同流：合同台账的交易对手方、金额
  - 发票流：进项/销项发票的开票方、受票方、金额
  - 资金流：银行流水的交易对手、金额、方向
  - 货物流：通过发票的商品/服务名称间接推断

本模块比较四流之间的一致性，输出归一化的匹配度得分。

商业语言输出：面向老板，用通俗语言说明匹配情况
技术语言输出：结构化数据，供风险引擎和其他模块消费
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

# ── 权重配置（可根据行业调整） ──
WEIGHTS = {
    "contract_invoice": 0.25,          # 合同-发票匹配权重
    "invoice_bank": 0.25,              # 发票-资金匹配权重
    "counterparty_consistency": 0.20,  # 交易对手一致性权重
    "amount_consistency": 0.10,        # 金额一致性权重
    "product_match": 0.20,             # 进销项品名匹配（Jaccard 相似度）
}

# 匹配阈值
EXACT_MATCH_THRESHOLD = Decimal("0.02")    # 金额差异 ≤ 2% 视为完全匹配
PARTIAL_MATCH_THRESHOLD = Decimal("0.10")  # 金额差异 ≤ 10% 视为部分匹配
MISMATCH_THRESHOLD = Decimal("0.30")       # 金额差异 > 30% 视为严重不匹配


@dataclass
class FourFlowMatchResult:
    """四流匹配结果"""
    overall_score: float = 0.0                      # 总体匹配度 0-100
    contract_invoice_score: float = 0.0             # 合同-发票匹配度
    invoice_bank_score: float = 0.0                 # 发票-资金匹配度
    counterparty_consistency_score: float = 0.0     # 交易对手一致性
    amount_consistency_score: float = 0.0           # 金额一致性
    product_match_score: float = 0.0                # 进销项品名 Jaccard 匹配度
    match_count: int = 0                            # 匹配成功记录总数（合同↔发票 + 发票↔资金）
    match_rate: float = 0.0                         # 整体匹配率 0-100
    contract_invoice_match_count: int = 0           # 匹配到发票的合同数量
    invoice_bank_match_count: int = 0               # 匹配到银行流水的发票数量
    details: list[dict] = field(default_factory=list)  # 逐笔差异详情
    risk_flags: list[str] = field(default_factory=list)  # 风险标记
    business_narrative: str = ""                    # 商业语言叙述
    technical_summary: dict[str, Any] = field(default_factory=dict)  # 技术语言摘要


@dataclass
class ContractRecord:
    contract_no: str
    counterparty: str
    amount: Decimal
    signing_date: date


@dataclass
class InvoiceRecord:
    invoice_no: str
    invoice_type: str  # "input" / "output"
    amount: Decimal
    total_amount: Decimal
    buyer_name: str
    seller_name: str
    product_name: str


@dataclass
class BankTransactionRecord:
    transaction_date: date
    amount: Decimal
    direction: str  # "inflow" / "outflow"
    account_type: str  # "corporate" / "personal"
    counterparty: str
    description: str
    is_declared: bool


def _normalize_key(value: str) -> str:
    """
    标准化匹配键，用于精确匹配前的预处理：

      - 去除首尾空白
      - 全角字符转半角（含全角空格）
      - casefold 统一大小写（兼容英文大小写差异）

    应用于 contract_no / invoice_no / counterparty / buyer_name / seller_name。
    """
    if value is None:
        return ""
    text = str(value).strip()
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:  # 全角空格
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:  # 全角 ASCII → 半角
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out).casefold()


def _is_counterparty_exact_match(name_a: str, name_b: str) -> bool:
    """检查两方名称是否完全一致（标准化后精确相等，不做子串/模糊匹配）"""
    if not name_a or not name_b:
        return False
    return _normalize_key(name_a) == _normalize_key(name_b)


def _calc_amount_match(a: Decimal, b: Decimal) -> float:
    """计算两个金额的匹配度得分 (0-1)"""
    if a == Decimal("0") and b == Decimal("0"):
        return 1.0
    if a == Decimal("0") or b == Decimal("0"):
        return 0.0
    diff = abs(a - b) / max(a, b)
    if diff <= EXACT_MATCH_THRESHOLD:
        return 1.0
    if diff <= PARTIAL_MATCH_THRESHOLD:
        return 1.0 - float(diff) * 5  # 线性衰减
    if diff <= MISMATCH_THRESHOLD:
        return 0.5 - float(diff - PARTIAL_MATCH_THRESHOLD) * 2
    return 0.0


def _tokenize_product_name(product_name: str) -> set[str]:
    """
    将商品名称分词为有意义的 token 集合，用于 Jaccard 相似度计算。

    处理策略：
      - 移除常见标点符号
      - 按空格、中文标点等切分
      - 过滤过短 token（<2 字符无区分度）
      - 大小写归一化
    """
    if not product_name:
        return set()
    import re
    cleaned = product_name.strip().casefold()
    # 按常见分隔符切分
    tokens = re.split(r'[\s,，./、\-—–()（）\[\]【】{}｜|:：;；]+', cleaned)
    return {t for t in tokens if len(t) >= 2}


def _calculate_product_jaccard(
    input_invoices: list["InvoiceRecord"],
    output_invoices: list["InvoiceRecord"],
) -> float:
    """
    计算进销项商品名称的 Jaccard 相似度。

    严格匹配逻辑：
      J(A, B) = |A ∩ B| / |A ∪ B|
      其中 A = 进项发票商品名称 token 集合
           B = 销项发票商品名称 token 集合

    Returns:
        float: Jaccard 系数 (0.0 ~ 1.0)，空数据返回 1.0
    """
    input_tokens: set[str] = set()
    for inv in input_invoices:
        if inv.invoice_type == "input":
            input_tokens.update(_tokenize_product_name(inv.product_name))

    output_tokens: set[str] = set()
    for inv in output_invoices:
        if inv.invoice_type == "output":
            output_tokens.update(_tokenize_product_name(inv.product_name))

    if not input_tokens and not output_tokens:
        return 1.0  # 双方均无数据，无法判断，不扣分

    if not input_tokens or not output_tokens:
        return 0.5  # 仅有一方数据，数据不足，返回中性分数（避免虚高完美匹配）

    intersection = input_tokens & output_tokens
    union = input_tokens | output_tokens

    if not union:
        return 1.0

    return len(intersection) / len(union)


def _generate_business_narrative(result: FourFlowMatchResult) -> str:
    """生成商业语言叙述"""
    score = result.overall_score
    if score >= 90:
        level = "非常健康"
    elif score >= 75:
        level = "基本合规"
    elif score >= 60:
        level = "存在疑点"
    elif score >= 40:
        level = "需要关注"
    else:
        level = "高风险"

    parts = [f"您的企业四流匹配度为 {score:.0f} 分，状态为「{level}」。"]
    if result.risk_flags:
        parts.append(f"系统发现 {len(result.risk_flags)} 个风险点：")
        for i, flag in enumerate(result.risk_flags[:5], 1):
            parts.append(f"  {i}. {flag}")
    else:
        parts.append("未发现明显四流不匹配风险。")
    return "\n".join(parts)


def calculate_four_flow_match(
    contracts: list[ContractRecord],
    invoices: list[InvoiceRecord],
    bank_transactions: list[BankTransactionRecord],
) -> FourFlowMatchResult:
    """
    计算四流匹配度（确定性算法，无随机因素，结果可复现）。

    Args:
        contracts: 合同台账列表
        invoices: 发票数据列表
        bank_transactions: 银行流水列表

    Returns:
        FourFlowMatchResult: 包含各维度得分、匹配数量/匹配率、风险标记、双语输出的匹配结果

    匹配规则（金税四期「四流一致」核查）：
      标准化：所有匹配键先经 _normalize_key 预处理 —— 去除首尾空白、
              全角转半角、casefold 统一大小写，然后做精确相等比较。
              不做子串包含、简称等模糊匹配，避免把不同主体误判为同一主体。

      1. 合同 ↔ 发票：合同 contract 与发票 invoice 匹配，当且仅当
           normalized(contract.counterparty) == normalized(invoice.buyer_name)
         或 normalized(contract.counterparty) == normalized(invoice.seller_name)；
         或 normalized(contract.contract_no) == normalized(invoice.invoice_no)
         （编号直连规则，适用于发票号携带合同号的业务场景）。
      2. 发票 ↔ 资金：发票 invoice 与银行流水 tx 匹配，当且仅当
           normalized(invoice.buyer_name) 或 normalized(invoice.seller_name)
           == normalized(tx.counterparty)。
      3. 合同 ↔ 资金（交易对手一致性）：normalized(contract.counterparty)
         与某笔流水的 normalized(counterparty) 精确相等。
      4. 金额一致性：合同/发票/资金三流总金额两两比对，偏差阈值见
         EXACT_MATCH_THRESHOLD / PARTIAL_MATCH_THRESHOLD / MISMATCH_THRESHOLD。
      5. 货物流：以进销项发票商品名称的 Jaccard 相似度间接推断。

    匹配数量与匹配率：
      - contract_invoice_match_count：匹配到发票的合同数（按规则 1）
      - invoice_bank_match_count：匹配到银行流水的发票数（按规则 2）
      - match_count = contract_invoice_match_count + invoice_bank_match_count
      - match_rate（0-100）：合同↔发票匹配率与发票↔资金匹配率的算术平均；
        单侧无数据（合同或发票为空）时不参与平均。
      - 空输入：视为 insufficient_data，overall_score=100、match_rate=100、
        match_count=0，不产生风险标记（无证据表明不匹配）。

    可复现性：本函数为纯函数，不依赖随机数、系统时间或外部可变状态；
    相同输入必然得到完全相同的输出。
    """
    # ── 负数校验 ──
    for ct in contracts:
        if ct.amount < 0:
            raise ValueError(f"合同金额不能为负数: {ct.contract_no} = {ct.amount}")
    for inv in invoices:
        if inv.amount < 0:
            raise ValueError(f"发票金额不能为负数: {inv.invoice_no} = {inv.amount}")
        if inv.total_amount < 0:
            raise ValueError(f"发票总金额不能为负数: {inv.invoice_no} = {inv.total_amount}")
    for tx in bank_transactions:
        if tx.amount < 0:
            raise ValueError(f"银行流水金额不能为负数: {tx.counterparty} = {tx.amount}")

    result = FourFlowMatchResult()

    # ── 边界条件：空输入 ──
    if not contracts and not invoices and not bank_transactions:
        result.overall_score = 100.0
        result.contract_invoice_score = 100.0
        result.invoice_bank_score = 100.0
        result.counterparty_consistency_score = 100.0
        result.amount_consistency_score = 100.0
        result.product_match_score = 100.0
        result.match_rate = 100.0
        result.business_narrative = "当前没有足够数据用于四流匹配分析，请补充业务数据。"
        result.technical_summary = {
            "status": "insufficient_data",
            "sample_count": 0,
            "match_stats": {
                "match_count": 0,
                "match_rate": result.match_rate,
                "contract_invoice": {"matched": 0, "total": 0},
                "invoice_bank": {"matched": 0, "total": 0},
            },
        }
        return result

    # ── 构建标准化精确匹配索引 ──
    contract_by_no: dict[str, ContractRecord] = {
        _normalize_key(ct.contract_no): ct for ct in contracts
    }
    invoice_by_no: dict[str, InvoiceRecord] = {
        _normalize_key(inv.invoice_no): inv for inv in invoices
    }
    invoice_by_cp: dict[str, list[InvoiceRecord]] = defaultdict(list)
    for inv in invoices:
        for name in (inv.buyer_name, inv.seller_name):
            key = _normalize_key(name)
            if key:
                invoice_by_cp[key].append(inv)
    bank_by_cp: dict[str, list[BankTransactionRecord]] = defaultdict(list)
    for tx in bank_transactions:
        key = _normalize_key(tx.counterparty)
        if key:
            bank_by_cp[key].append(tx)

    # ── 1. 合同-发票精确匹配 ──
    ci_scores: list[float] = []
    ci_details: list[dict] = []
    ci_matched = 0
    for ct in contracts:
        matched_inv: InvoiceRecord | None = None
        ct_cp_key = _normalize_key(ct.counterparty)
        candidates: list[InvoiceRecord] = invoice_by_cp.get(ct_cp_key, [])
        # 补充规则：发票号与合同号标准化后完全相等 → 编号直连匹配
        if not candidates:
            ct_no_key = _normalize_key(ct.contract_no)
            if ct_no_key in invoice_by_no:
                candidates = [invoice_by_no[ct_no_key]]
        if candidates:
            matched_inv = max(
                candidates,
                key=lambda inv: _calc_amount_match(ct.amount, inv.total_amount),
            )
        if matched_inv is not None:
            ci_matched += 1
            amt_score = _calc_amount_match(ct.amount, matched_inv.total_amount)
            ci_scores.append(amt_score if amt_score > 0 else 0.3)
            diff_amount = abs(float(ct.amount) - float(matched_inv.total_amount))
            max_amount = max(float(ct.amount), float(matched_inv.total_amount))
            ci_details.append({
                "contract_no": ct.contract_no,
                "counterparty": ct.counterparty,
                "contract_amount": float(ct.amount),
                "invoice_no": matched_inv.invoice_no,
                "invoice_amount": float(matched_inv.total_amount),
                "counterparty_match": True,
                "amount_match_score": round(amt_score, 4),
                "match_status": "matched",
                "diff_amount": round(diff_amount, 2),
                "diff_rate": round(diff_amount / max_amount, 4) if max_amount > 0 else 0.0,
            })
        else:
            ci_scores.append(0.0)
            ci_details.append({
                "contract_no": ct.contract_no,
                "counterparty": ct.counterparty,
                "contract_amount": float(ct.amount),
                "invoice_no": None,
                "invoice_amount": 0,
                "counterparty_match": False,
                "amount_match_score": 0.0,
                "match_status": "unmatched",
                "diff_amount": round(float(ct.amount), 2),
                "diff_rate": 1.0,
            })
            result.risk_flags.append(f"合同 {ct.contract_no}（金额 {ct.amount}元）未找到对应发票")

    result.contract_invoice_score = round(
        sum(ci_scores) / len(ci_scores) * 100 if ci_scores else 100.0, 2
    )
    result.contract_invoice_match_count = ci_matched

    # ── 2. 发票-资金精确匹配 ──
    ib_scores: list[float] = []
    ib_details: list[dict] = []
    ib_matched = 0
    for inv in invoices:
        inv_cp_keys = {
            _normalize_key(inv.buyer_name),
            _normalize_key(inv.seller_name),
        } - {""}
        best_score = 0.0
        matched_tx: BankTransactionRecord | None = None
        for key in inv_cp_keys:
            for tx in bank_by_cp.get(key, []):
                amt_score = _calc_amount_match(inv.total_amount, tx.amount)
                if amt_score > best_score:
                    best_score = amt_score
                    matched_tx = tx
        if matched_tx is not None:
            ib_matched += 1
            diff_amount = abs(float(inv.total_amount) - float(matched_tx.amount))
            max_amount = max(float(inv.total_amount), float(matched_tx.amount))
            diff_rate = round(diff_amount / max_amount, 4) if max_amount > 0 else 0.0
        else:
            diff_amount = round(float(inv.total_amount), 2)
            diff_rate = 1.0 if float(inv.total_amount) > 0 else 0.0
        ib_scores.append(best_score)
        ib_details.append({
            "invoice_no": inv.invoice_no,
            "invoice_amount": float(inv.total_amount),
            "matched_bank_counterparty": matched_tx.counterparty if matched_tx else None,
            "matched_bank_amount": float(matched_tx.amount) if matched_tx else 0,
            "score": round(best_score, 4),
            "match_status": "matched" if matched_tx is not None else "unmatched",
            "diff_amount": diff_amount,
            "diff_rate": diff_rate,
        })
        if best_score < 0.5 and inv.total_amount > Decimal("0"):
            result.risk_flags.append(
                f"发票 {inv.invoice_no}（金额 {inv.total_amount}元）与银行流水金额差异较大"
            )

    result.invoice_bank_score = round(
        sum(ib_scores) / len(ib_scores) * 100 if ib_scores else 100.0, 2
    )
    result.invoice_bank_match_count = ib_matched

    # ── 3. 交易对手一致性（标准化精确匹配）──
    cp_scores: list[float] = []
    # 合同 vs 银行
    for ct in contracts:
        ct_cp_key = _normalize_key(ct.counterparty)
        found = bool(ct_cp_key and bank_by_cp.get(ct_cp_key))
        cp_scores.append(1.0 if found else 0.0)
    # 无合同数据时，回退检查发票 vs 银行
    if not contracts and invoices:
        for inv in invoices:
            inv_cp_keys = {
                _normalize_key(inv.buyer_name),
                _normalize_key(inv.seller_name),
            } - {""}
            found = any(bank_by_cp.get(k) for k in inv_cp_keys)
            cp_scores.append(1.0 if found else 0.0)

    result.counterparty_consistency_score = round(
        sum(cp_scores) / len(cp_scores) * 100 if cp_scores else 100.0, 2
    )

    # ── 4. 金额一致性（各流总金额比对） ──
    total_contract = sum(ct.amount for ct in contracts)
    total_invoice = sum(inv.total_amount for inv in invoices)
    total_bank = sum(tx.amount for tx in bank_transactions)

    if total_contract > 0 or total_invoice > 0 or total_bank > 0:
        amt_scores = []
        if total_contract > 0 and total_invoice > 0:
            amt_scores.append(_calc_amount_match(total_contract, total_invoice))
        if total_invoice > 0 and total_bank > 0:
            amt_scores.append(_calc_amount_match(total_invoice, total_bank))
        result.amount_consistency_score = round(
            sum(amt_scores) / len(amt_scores) * 100 if amt_scores else 100.0, 2
        )
    else:
        result.amount_consistency_score = 100.0

    # ── 5. 进销项品名匹配（Jaccard 相似度） ──
    input_invs = [inv for inv in invoices if inv.invoice_type == "input"]
    output_invs = [inv for inv in invoices if inv.invoice_type == "output"]

    jaccard = _calculate_product_jaccard(input_invs, output_invs)
    result.product_match_score = round(jaccard * 100, 2)

    # 品名匹配风险标记（仅当进销两侧均有数据时才有比对依据）
    if input_invs and output_invs:
        if jaccard < 0.3:
            result.risk_flags.append(
                f"进销项品名匹配度极低（{jaccard:.0%}），"
                "进项原材料/商品与销项产品几乎无交集，可能存在进销发票品名不一致或隐匿收入"
            )
        elif jaccard < 0.6:
            result.risk_flags.append(
                f"进销项品名匹配度偏低（{jaccard:.0%}），"
                "进项产品与销项产品对应关系可疑"
            )

    # ── 匹配数量与匹配率 ──
    result.match_count = ci_matched + ib_matched
    ci_rate = ci_matched / len(contracts) if contracts else None
    ib_rate = ib_matched / len(invoices) if invoices else None
    rates = [r for r in (ci_rate, ib_rate) if r is not None]
    result.match_rate = round(sum(rates) / len(rates) * 100, 2) if rates else 100.0

    # ── 整体评分 ──
    result.overall_score = round(
        result.contract_invoice_score * WEIGHTS["contract_invoice"] +
        result.invoice_bank_score * WEIGHTS["invoice_bank"] +
        result.counterparty_consistency_score * WEIGHTS["counterparty_consistency"] +
        result.amount_consistency_score * WEIGHTS["amount_consistency"] +
        result.product_match_score * WEIGHTS["product_match"],
        2,
    )

    # 私卡交易检测
    personal_txs = [tx for tx in bank_transactions if tx.account_type == "personal"]
    undeclared_personal = [tx for tx in personal_txs if not tx.is_declared]
    if undeclared_personal:
        total_personal = sum(tx.amount for tx in undeclared_personal)
        result.risk_flags.append(f"发现 {len(undeclared_personal)} 笔未申报私卡交易，共计 {total_personal} 元")

    result.details = ci_details + ib_details
    result.business_narrative = _generate_business_narrative(result)
    result.technical_summary = {
        "scores": {
            "contract_invoice": result.contract_invoice_score,
            "invoice_bank": result.invoice_bank_score,
            "counterparty_consistency": result.counterparty_consistency_score,
            "amount_consistency": result.amount_consistency_score,
            "product_match": result.product_match_score,
            "overall": result.overall_score,
        },
        "sample_count": {
            "contracts": len(contracts),
            "invoices": len(invoices),
            "bank_transactions": len(bank_transactions),
        },
        "match_stats": {
            "match_count": result.match_count,
            "match_rate": result.match_rate,
            "contract_invoice": {"matched": ci_matched, "total": len(contracts)},
            "invoice_bank": {"matched": ib_matched, "total": len(invoices)},
        },
        "weights": WEIGHTS,
        "risk_flags_count": len(result.risk_flags),
    }

    return result
