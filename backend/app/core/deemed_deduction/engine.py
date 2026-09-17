"""
乳业农产品「核定扣除引擎」（V4 §4.2 的工程化落点）

法律依据（全部经官方原文核实，规则时效由 rule_governance 注册表闸门管理）：
  - 财税〔2012〕38号（试点主规则；附件1 计算办法；附件2 全国统一单耗）
      · 附件1：投入产出法 / 成本法；扣除率为销售货物的适用税率（第七条）
      · 第十三条：生产货物场景申请核定并公告；直接销售 / 不构成货物实体场景备案制
      · 第一条：试点纳税人购进农产品无论是否用于生产上述产品，均按核定扣除办法抵扣
  - 财政部 税务总局公告2026年第10号第五条第（二）项：非试点普通抵扣路径三情形 + 合作社免税农产品
  - 财政部 税务总局公告2026年第9号附件1：『鲜奶』范围注释（巴氏杀菌乳/灭菌乳在内；
    酸奶、调制乳等加工奶制品不在内）

判定顺序（V4 §4.2 产品级判定流程，与 G2/E2 审查结论一致）：
  纳税人/业务身份（是否试点主体） → 抵扣路径 → 产品税收分类（9号公告范围）
  → 产品单耗（38号文附件2） → 扣除率（38号文附件1第七条） → Decimal 金额计算

铁律：
  - zen-engine 只做定性路由（资格/范围/兜底转人工），不承担任何金额运算；
  - 金额与税额全部由本模块 Decimal 实现，量化 ROUND_HALF_UP 至分；
  - 每次计算产出确定性 calc_id 与参数快照（审计证据链）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from app.core.rule_governance import (
    CalculationResult,
    ManualRoute,
    RuleExecutor,
)

_STANDARDS_PATH = Path(__file__).parent / "fixtures" / "consumption_standards.json"

# ── 精确小数常量（金额计算禁用 float） ──
RATE_09 = Decimal("0.09")
ONE = Decimal("1")
_CENT = Decimal("0.01")


def _q2(value: Decimal) -> Decimal:
    """量化到分（四舍五入，银行家偏差可控口径与申报一致）"""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def load_standards(path: Path | str | None = None) -> dict:
    """加载单耗标准库 / 鲜奶范围 / 非试点路径 / 省级补丁位"""
    return json.loads(
        (_STANDARDS_PATH if path is None else Path(path)).read_text(encoding="utf-8")
    )


# ── 结果对象 ──
@dataclass(frozen=True)
class PathDecision:
    """抵扣路径判定结果"""

    path_code: str          # deemed / general_invoice / small_scale_3pct / sales_purchase / coop / manual
    rate: Optional[Decimal]  # 该路径适用的扣除率（①情形为 None：凭注明税额）
    rule_id: str
    basis: str              # 法规依据原文摘录


@dataclass(frozen=True)
class ProductScopeDecision:
    """产品『鲜奶』范围判定结果（2026年第9号公告附件1）"""

    in_scope: Optional[bool]  # True/False；None=未知 → 转人工
    product_name: str
    matched: str = ""
    note: str = ""


@dataclass
class DeemedCalcRequest:
    """核定扣除计算请求（业务事实，全部为可快照字段）"""

    entity_is_pilot: bool                 # 是否核定扣除试点主体（液体乳及乳制品 C1440）
    product_kind: str                     # uht / pasteurized
    animal: str                           # cow / goat
    high_protein: bool
    sales_quantity: Decimal               # 当期销售货物数量（吨）
    avg_purchase_price: Decimal           # 购进农产品平均购买单价（万元/吨，与数量同口径）
    product_name: str = ""                # 产品名称（用于范围判定演示）
    voucher_type: str = "sales_or_purchase_invoice"  # 非试点路径凭证类型


@dataclass
class EngineResult:
    """引擎输出（含审计证据链要素）"""

    route: str                            # auto / manual
    reason: str = ""
    path: Optional[PathDecision] = None
    scope: Optional[ProductScopeDecision] = None
    coefficient: Optional[Decimal] = None
    coefficient_rule_id: str = ""
    rate: Optional[Decimal] = None
    input_vat: Optional[Decimal] = None   # 当期允许抵扣的农产品增值税进项税额
    formula: str = ""
    calc_id: str = ""
    rule_ids: tuple[str, ...] = ()
    params_snapshot: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# ── 第 1 步：纳税人/业务身份 → 抵扣路径 ──
def identify_purchase_path(
    is_pilot: bool, voucher_type: str, standards: Optional[dict] = None
) -> PathDecision:
    """
    路径判定（V3.1 采纳 E2-C 结论）：
      试点范围内不得改按普通凭票路径自由选择；非试点主体才进入普通抵扣路径分情形。
    """
    if is_pilot:
        return PathDecision(
            path_code="deemed",
            rate=None,  # 扣除率由产出货物适用税率决定（附件1第七条），在第 4 步确定
            rule_id="AGRI-DEEM-001",
            basis="财税〔2012〕38号：试点纳税人购进农产品按核定扣除办法抵扣（无论是否用于生产上述产品）",
        )
    cases = (standards or load_standards())["invoice_path_cases"]
    if voucher_type not in cases:
        return PathDecision(
            path_code="manual", rate=None, rule_id="VAT-INPUT-STD-001",
            basis=f"未知凭证类型 {voucher_type}，转人工判定",
        )
    case = cases[voucher_type]
    rate = Decimal(case["rate"]) if case["rate"] is not None else None
    return PathDecision(
        path_code=voucher_type, rate=rate, rule_id=case["rule_id"], basis=case["basis"]
    )


# ── 第 2 步：产品『鲜奶』范围判定（定性规则下沉 zen 决策图；此处为快速判定器） ──
def _norm(text: str) -> str:
    return (text or "").strip().casefold().replace("（", "(").replace("）", ")")


def classify_product_scope(
    product_name: str, standards: Optional[dict] = None
) -> ProductScopeDecision:
    """按 2026年第9号公告附件1 范围注释判定：巴氏/灭菌 → in；酸奶/调制乳/奶酪/奶油 → out"""
    std = standards or load_standards()
    key = _norm(product_name)
    scope = std["fresh_milk_scope"]
    for entry in scope["in_scope"]:
        names = [_norm(entry["product_name"]), *(_norm(a) for a in entry.get("aliases", []))]
        if key and any(name and name in key for name in names):
            return ProductScopeDecision(
                in_scope=True, product_name=product_name, matched=entry["product_name"],
                note="属于『鲜奶』9%范围（2026年第9号公告附件1）",
            )
    for entry in scope["out_scope"]:
        names = [_norm(entry["product_name"]), *(_norm(a) for a in entry.get("aliases", []))]
        if key and any(name and name in key for name in names):
            return ProductScopeDecision(
                in_scope=False, product_name=product_name, matched=entry["product_name"],
                note=entry.get("reason", "不属于『鲜奶』范围"),
            )
    return ProductScopeDecision(
        in_scope=None, product_name=product_name,
        note="未命中范围注释，转人工判定（禁止默认套用 9%）",
    )


# ── 第 3 步：单耗标准库 ──
def pick_coefficient(
    product_kind: str, animal: str, high_protein: bool, standards: Optional[dict] = None
) -> tuple[Optional[Decimal], str]:
    """返回 (单耗系数, rule_id)；无匹配标准 → (None, "") 由上层转人工"""
    std = standards or load_standards()
    for item in std["national_coefficients"]:
        if (
            item["product_kind"] == product_kind
            and item["animal"] == animal
            and bool(item["high_protein"]) == bool(high_protein)
        ):
            return Decimal(item["coefficient"]), item["rule_id"]
    return None, ""


# ── 第 4 步：扣除率路由（zen 决策图：AGRI-DEEM-RATE-001 定性路由 + 兜底转人工） ──
def build_rate_routing_graph() -> dict:
    """产出货物适用税率 → 核定扣除率（附件1第七条），兜底 ROUTE_TO_MANUAL"""
    return {
        "nodes": [
            {"id": "in1", "type": "inputNode", "name": "facts", "position": {"x": 0, "y": 0}, "content": {}},
            {"id": "dt1", "type": "decisionTableNode", "name": "deemed_rate_router",
             "position": {"x": 200, "y": 0},
             "content": {
                 "hitPolicy": "first",
                 "inputs": [
                     {"id": "i1", "name": "产出货物适用税率", "field": "output_vat"},
                     {"id": "i2", "name": "产品鲜奶范围", "field": "in_scope"},
                 ],
                 "outputs": [
                     {"id": "o1", "name": "扣除率", "field": "result.rate"},
                     {"id": "o2", "name": "路由说明", "field": "result.route_note"},
                 ],
                 "rules": [
                     {"_id": "r1", "_description": "鲜奶范围内且产出税率9% → 扣除率9%（附件1第七条）",
                      "i1": "== 9", "i2": "== true", "o1": "0.09",
                      "o2": "'AGRI-DEEM-RATE-001: 扣除率=销售货物适用税率'"},
                     {"_id": "r2", "_description": "鲜奶范围外（酸奶/调制乳等）→ 禁止套用，转人工",
                      "i1": "", "i2": "== false", "o1": "null", "o2": "'ROUTE_TO_MANUAL: 不属于鲜奶9%范围'"},
                     {"_id": "r3", "_description": "其他税率/未知 → 兜底转人工",
                      "i1": "", "i2": "", "o1": "null", "o2": "'ROUTE_TO_MANUAL: 未命中范围注释'"},
                 ],
                 "passThrough": True, "inputField": None, "outputPath": None,
                 "executionMode": "single"}},
        ],
        "edges": [{"id": "ed1", "sourceId": "in1", "targetId": "dt1", "type": "edge"}],
    }


# ── 第 5 步：Decimal 金额计算（38号文附件1 法定公式） ──
def calc_input_output_method(
    sales_quantity: Decimal, coefficient: Decimal,
    avg_purchase_price: Decimal, deduction_rate: Decimal,
) -> tuple[Decimal, str]:
    """
    投入产出法：当期允许抵扣的农产品增值税进项税额
      = 当期销售货物数量 × 农产品单耗数量 × 购买农产品平均单价 × 扣除率 / (1 + 扣除率)
    """
    gross = sales_quantity * coefficient * avg_purchase_price
    vat = _q2(gross * deduction_rate / (ONE + deduction_rate))
    formula = (
        "投入产出法：进项税额 = 销售数量 × 单耗 × 平均单价 × 扣除率 / (1 + 扣除率)"
        "（财税〔2012〕38号附件1）"
    )
    return vat, formula


def calc_cost_method(
    main_business_cost: Decimal, consumption_ratio: Decimal, deduction_rate: Decimal
) -> tuple[Decimal, str]:
    """
    成本法：当期允许抵扣的农产品增值税进项税额
      = 当期主营业务成本 × 农产品耗用率 × 扣除率 / (1 + 扣除率)
    （农产品耗用率 = 上年投入生产的农产品外购金额 / 上年生产成本，次年1月内据实调整）
    """
    gross = main_business_cost * consumption_ratio
    vat = _q2(gross * deduction_rate / (ONE + deduction_rate))
    formula = (
        "成本法：进项税额 = 主营业务成本 × 农产品耗用率 × 扣除率 / (1 + 扣除率)"
        "（财税〔2012〕38号附件1）"
    )
    return vat, formula


def calc_invoice_path_amount(base_amount: Decimal, rate: Decimal) -> tuple[Decimal, str]:
    """非试点路径金额：②发票注明金额 × 9% / ③买价 × 9%（2026年第10号公告第五条第（二）项）"""
    vat = _q2(base_amount * rate)
    return vat, f"普通抵扣路径：计税基础 × {rate}（VAT-INPUT-STD-001）"


# ── 主流程：核定扣除计算（一期演示口径） ──
def run_deemed_calculation(
    request: DeemedCalcRequest,
    executor: Optional[RuleExecutor] = None,
    on_date: Optional[date] = None,
    standards: Optional[dict] = None,
) -> EngineResult:
    """
    端到端核定扣除计算：闸门 → 路径 → 范围 → 单耗 → 扣除率 → Decimal 金额。

    任一步无法确定性完成 → route="manual" 并给出原因（禁止默认套用/编造结果）。
    """
    std = standards or load_standards()
    executor = executor if executor is not None else RuleExecutor()
    result = EngineResult(route="manual")

    # 1) 抵扣路径
    path = identify_purchase_path(request.entity_is_pilot, request.voucher_type, std)
    result.path = path
    if path.path_code == "manual":
        result.reason = path.basis
        return result

    # 2) 非试点普通抵扣路径：凭注明税额（①）不在此计算；②③按基础金额×扣除率
    if not request.entity_is_pilot:
        if path.rate is None:
            result.reason = (
                f"{path.basis}——以凭证注明税额为准，本引擎不代算，请取凭证税额"
            )
            return result
        vat, formula = calc_invoice_path_amount(request.avg_purchase_price, path.rate)
        result.route = "auto"
        result.rate = path.rate
        result.input_vat = vat
        result.formula = formula
        result.rule_ids = (path.rule_id,)
        result.notes.append(path.basis)
        result.params_snapshot = {
            "path": path.path_code, "base_amount": str(request.avg_purchase_price),
            "rate": str(path.rate), "voucher_type": request.voucher_type,
        }
        result.calc_id = f"NONPILOT-{path.rule_id}-{_q2(request.avg_purchase_price * path.rate)}"
        return result

    # 3) 试点主体：产品『鲜奶』范围判定
    scope = classify_product_scope(request.product_name, std)
    result.scope = scope
    if scope.in_scope is not True:
        result.reason = scope.note
        return result

    # 4) 单耗标准
    coefficient, coef_rule_id = pick_coefficient(
        request.product_kind, request.animal, request.high_protein, std
    )
    result.coefficient, result.coefficient_rule_id = coefficient, coef_rule_id
    if coefficient is None:
        result.reason = "无全国统一单耗标准；按38号文第十二条属省级/个案核定场景，转人工"
        return result

    # 5) 扣除率路由（zen 决策图，规则 AGRI-DEEM-RATE-001）
    routing = executor.execute(
        rule_ids=["AGRI-DEEM-001", "AGRI-DEEM-RATE-001", coef_rule_id],
        graph=build_rate_routing_graph(),
        context={
            "output_vat": 9,  # 巴氏/灭菌乳属『鲜奶』→ 现行9%税率货物范围（演示口径）
            "in_scope": True,
        },
        on_date=on_date,
    )
    if isinstance(routing, ManualRoute):
        result.reason = f"规则闸门挂起：{routing.rule_id} {routing.reason}"
        return result
    # zen 图输出因 passThrough 嵌套在 result["result"] 命名空间下（与输入区分）
    route_note = str(routing.result.get("result", {}).get("route_note", ""))
    if route_note.startswith("ROUTE_TO_MANUAL"):
        result.reason = route_note
        return result

    rate = Decimal(str(routing.result["result"]["rate"]))
    vat, formula = calc_input_output_method(
        request.sales_quantity, coefficient, request.avg_purchase_price, rate
    )
    result.route = "auto"
    result.rate = rate
    result.input_vat = vat
    result.formula = formula
    result.calc_id = routing.calc_id
    result.rule_ids = routing.rule_ids
    result.params_snapshot = {
        **routing.params_snapshot,
        "sales_quantity": str(request.sales_quantity),
        "coefficient": str(coefficient),
        "avg_purchase_price": str(request.avg_purchase_price),
        "input_vat": str(vat),
        "product_name": request.product_name,
    }
    result.notes.append(
        "试点范围内不得改按普通凭票路径自由选择（38号文第一条）"
    )
    return result
