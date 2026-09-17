"""乳业农产品「核定扣除引擎」（V4 §4.2）"""
from app.core.rule_governance import RuleExecutor  # noqa: F401
from app.core.deemed_deduction.engine import (  # noqa: F401
    DeemedCalcRequest,
    EngineResult,
    PathDecision,
    ProductScopeDecision,
    calc_cost_method,
    calc_input_output_method,
    calc_invoice_path_amount,
    classify_product_scope,
    identify_purchase_path,
    load_standards,
    pick_coefficient,
    run_deemed_calculation,
)
