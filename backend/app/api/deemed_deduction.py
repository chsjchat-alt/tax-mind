"""
核定扣除计算 API（V4 §4.2 引擎的首个生产调用链路）

POST /api/v1/deemed-deduction/calculate
  乳业农产品核定扣除端到端计算：路径判定 → 『鲜奶』范围 → 单耗 →
  扣除率路由（zen 决策图）→ Decimal 金额。
  自动路由成功时将 calc_id + 参数快照挂载到请求，由审计中间件写入
  audit_logs（审计证据链落库，V4 §二）。

铁律（与引擎一致）：zen-engine 只做定性路由；金额全部 Decimal 精确到分；
任一步无法确定性完成 → route="manual" 并给出原因，禁止默认套用。
"""
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import error_response, require_viewer, success_response
from app.core.deemed_deduction.engine import (
    DeemedCalcRequest,
    EngineResult,
    run_deemed_calculation,
)
from app.models.user import User
from app.services.audit_evidence import attach_calc_evidence

router = APIRouter(tags=["核定扣除"])


class DeemedCalcPayload(BaseModel):
    """核定扣除计算请求（数值字段用字符串承载，保 Decimal 精度）"""

    entity_is_pilot: bool = Field(
        True, description="是否核定扣除试点主体（液体乳及乳制品 C1440）"
    )
    product_kind: str = Field(
        "uht", description="产品类型：uht（灭菌乳）/ pasteurized（巴氏杀菌乳）"
    )
    animal: str = Field("cow", description="原料奶来源：cow / goat")
    high_protein: bool = Field(False, description="是否高蛋白产品（单耗标准分档）")
    sales_quantity: str = Field(
        ..., description="当期销售货物数量（吨），数字字符串"
    )
    avg_purchase_price: str = Field(
        ..., description="购进农产品平均购买单价（万元/吨），数字字符串"
    )
    product_name: str = Field(
        "", description="产品名称（用于『鲜奶』范围判定，如：巴氏杀菌鲜牛奶）"
    )
    voucher_type: str = Field(
        "sales_or_purchase_invoice",
        description="非试点路径凭证类型（sales_or_purchase_invoice / "
        "purchase_invoice / special_deduction_invoice / coop_invoice）",
    )


def _serialize_result(result: EngineResult) -> dict:
    """引擎结果 → JSON dict（Decimal 全部转字符串，保留精确口径）"""
    payload: dict = {
        "route": result.route,
        "reason": result.reason,
        "input_vat": str(result.input_vat) if result.input_vat is not None else None,
        "formula": result.formula,
        "calc_id": result.calc_id,
        "rule_ids": list(result.rule_ids),
        "params_snapshot": result.params_snapshot,
        "notes": result.notes,
    }
    if result.path is not None:
        payload["path"] = {
            "path_code": result.path.path_code,
            "rate": str(result.path.rate) if result.path.rate is not None else None,
            "rule_id": result.path.rule_id,
            "basis": result.path.basis,
        }
    if result.scope is not None:
        payload["scope"] = {
            "in_scope": result.scope.in_scope,
            "product_name": result.scope.product_name,
            "matched": result.scope.matched,
            "note": result.scope.note,
        }
    if result.coefficient is not None:
        payload["coefficient"] = str(result.coefficient)
        payload["coefficient_rule_id"] = result.coefficient_rule_id
    if result.rate is not None:
        payload["rate"] = str(result.rate)
    return payload


@router.post("/deemed-deduction/calculate")
async def calculate_deemed_deduction(
    payload: DeemedCalcPayload,
    request: Request,
    current_user: User = Depends(require_viewer),
):
    """核定扣除端到端计算（viewer+；自动路由时证据链落库审计日志）"""
    # ── 数值解析：字符串 → Decimal（拒绝非法数字与负数） ──
    try:
        sales_quantity = Decimal(payload.sales_quantity.strip())
        avg_purchase_price = Decimal(payload.avg_purchase_price.strip())
    except InvalidOperation:
        return error_response(40001, "数量/单价必须是合法数字字符串")
    if sales_quantity <= 0 or avg_purchase_price <= 0:
        return error_response(40001, "数量与单价必须为正数")

    calc_request = DeemedCalcRequest(
        entity_is_pilot=payload.entity_is_pilot,
        product_kind=payload.product_kind,
        animal=payload.animal,
        high_protein=payload.high_protein,
        sales_quantity=sales_quantity,
        avg_purchase_price=avg_purchase_price,
        product_name=payload.product_name,
        voucher_type=payload.voucher_type,
    )

    result = run_deemed_calculation(calc_request)

    # ── 审计证据链：自动路由成功 → calc_id + 参数快照挂载到请求 ──
    if result.route == "auto" and result.calc_id:
        attach_calc_evidence(
            request,
            calc_id=result.calc_id,
            params_snapshot=result.params_snapshot,
            rule_ids=result.rule_ids,
            action="deemed_deduction.calculate",
        )

    return success_response({
        "result": _serialize_result(result),
        "is_auto": result.route == "auto",
    })
