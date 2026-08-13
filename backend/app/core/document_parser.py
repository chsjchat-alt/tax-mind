"""
文档解析引擎

支持从上传的 Excel 文件中解析会计凭证、试算平衡表、财务报表、税务台账，
输出合规校验器所需的标准数据结构。

Excel 模板包含以下 Sheet：
  - 会计凭证  → list[dict]   (vouchers)
  - 试算平衡表 → dict         (trial_balance)
  - 财务报表   → dict         (financial_statements)
  - 税务台账   → dict         (tax_ledger)
"""

import io
import logging
from dataclasses import dataclass, field
from typing import Any

import openpyxl

_logger = logging.getLogger(__name__)


# ── 输出数据结构 ──
@dataclass
class ParseResult:
    """解析结果"""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def vouchers(self) -> list[dict]:
        return self.data.get("monthly_vouchers", [])

    @property
    def trial_balance(self) -> dict:
        return self.data.get("trial_balance", {})

    @property
    def financial_statements(self) -> dict:
        return self.data.get("financial_statements", {})

    @property
    def tax_ledger(self) -> dict:
        return self.data.get("tax_ledger", {})


# ── 会计凭证列映射 ──
VOUCHER_COLUMNS = {
    "凭证号": "voucher_no",
    "日期": "voucher_date",
    "摘要": "description",
    "科目编码": "account_code",
    "科目名称": "account_name",
    "借方金额": "debit_amount",
    "贷方金额": "credit_amount",
    "方向": "direction",
}

# ── 试算平衡表列映射 ──
TB_COLUMNS = {
    "科目编码": "account_code",
    "科目名称": "account_name",
    "期初余额": "opening_balance",
    "期末余额": "closing_balance",
}

# ── 财务报表必须的字段 ──
FS_REQUIRED_FIELDS = [
    "total_assets",           # 资产总计
    "total_liabilities",      # 负债总计
    "流动资产",               # current_assets
    "流动负债",               # current_liabilities
    "一、营业收入",           # revenue
]

# ── 税务台账必须的字段 ──
TAX_REQUIRED_FIELDS = [
    ("vat", "output_tax"),
    ("vat", "input_tax"),
    ("vat", "net_payable"),
    ("vat", "declared_revenue"),
    ("corporate_income_tax", "tax_payable"),
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float"""
    if value is None:
        return default
    try:
        return float(str(value).replace(",", "").replace("，", "").strip())
    except (ValueError, TypeError):
        return default


def _safe_str(value: Any, default: str = "") -> str:
    """安全转换为 str"""
    if value is None:
        return default
    return str(value).strip()


def parse_vouchers_sheet(ws) -> list[dict]:
    """
    解析「会计凭证」Sheet。

    支持两种格式：
      格式A（逐行分录）：每行一条分录，同一凭证的多行通过"凭证号"聚合
      格式B（汇总凭证）：每行一条凭证摘要，借方/贷方金额分散在多列

    输出格式：
      [
        {
          "voucher_no": "记-2025-06-001",
          "voucher_date": "2025-06-08",
          "description": "销售商品给XX公司",
          "entries": [
            {"direction": "debit", "account_code": "1002", "account_name": "银行存款", "amount": 263304.31},
            {"direction": "credit", "account_code": "6001", "account_name": "主营业务收入", "amount": 233012.66},
          ],
          "is_posted": True
        }
      ]
    """
    vouchers: list[dict] = []
    rows = list(ws.iter_rows(min_row=1, values_only=True))

    if len(rows) < 2:
        return vouchers

    # 解析表头
    headers = [_safe_str(h) for h in rows[0]]
    col_map: dict[str, int] = {}
    for idx, h in enumerate(headers):
        if h in VOUCHER_COLUMNS:
            col_map[VOUCHER_COLUMNS[h]] = idx
        # 也支持直接用英文字段名
        if h in ("voucher_no", "voucher_date", "description",
                 "account_code", "account_name", "debit_amount", "credit_amount", "direction"):
            col_map[h] = idx

    # 检测格式：是否有 account_code 列（格式A）还是只有凭证号+摘要+金额（格式B）
    is_format_a = "account_code" in col_map

    if not is_format_a:
        _logger.warning("会计凭证 Sheet 未检测到「科目编码」列，尝试按汇总格式解析")
        return _parse_vouchers_summary(ws, col_map, rows)

    # ── 格式A：逐行分录 ──
    # 按凭证号分组
    voucher_groups: dict[str, dict] = {}
    for row in rows[1:]:
        if all(v is None or str(v).strip() == "" for v in row):
            continue

        voucher_no = _safe_str(row[col_map["voucher_no"]]) if "voucher_no" in col_map else ""
        if not voucher_no:
            continue

        direction = _safe_str(row[col_map["direction"]]) if "direction" in col_map else ""
        debit_amt = _safe_float(row[col_map["debit_amount"]]) if "debit_amount" in col_map else 0
        credit_amt = _safe_float(row[col_map["credit_amount"]]) if "credit_amount" in col_map else 0

        # 推断方向
        if not direction:
            if debit_amt > 0:
                direction = "debit"
            elif credit_amt > 0:
                direction = "credit"

        amount = debit_amt if debit_amt > 0 else credit_amt

        entry = {
            "direction": direction,
            "account_code": _safe_str(row[col_map["account_code"]]) if "account_code" in col_map else "",
            "account_name": _safe_str(row[col_map["account_name"]]) if "account_name" in col_map else "",
            "amount": amount,
        }

        if voucher_no not in voucher_groups:
            voucher_groups[voucher_no] = {
                "voucher_no": voucher_no,
                "voucher_date": _safe_str(row[col_map["voucher_date"]]) if "voucher_date" in col_map else "",
                "description": _safe_str(row[col_map["description"]]) if "description" in col_map else "",
                "entries": [],
                "is_posted": True,
            }

        voucher_groups[voucher_no]["entries"].append(entry)

    vouchers = list(voucher_groups.values())
    _logger.info("解析会计凭证: %d 笔凭证, %d 条分录",
                 len(vouchers), sum(len(v["entries"]) for v in vouchers))
    return vouchers


def _parse_vouchers_summary(ws, col_map: dict, rows: list) -> list[dict]:
    """格式B：每行一条凭证摘要，从列名推断科目和金额"""
    vouchers: list[dict] = []
    headers = [_safe_str(h) for h in rows[0]]

    # 识别金额列（借方/贷方）
    debit_cols: dict[str, int] = {}   # account_code -> col_index
    credit_cols: dict[str, int] = {}

    for idx, h in enumerate(headers):
        if "借方" in h or "debit" in h.lower():
            # 尝试提取科目编码
            code = _extract_account_code(h)
            if code:
                debit_cols[code] = idx
        elif "贷方" in h or "credit" in h.lower():
            code = _extract_account_code(h)
            if code:
                credit_cols[code] = idx

    voucher_no_col = col_map.get("voucher_no", 0)
    date_col = col_map.get("voucher_date", 1)
    desc_col = col_map.get("description", 2)

    for row in rows[1:]:
        if all(v is None or str(v).strip() == "" for v in row):
            continue

        voucher_no = _safe_str(row[voucher_no_col]) if voucher_no_col < len(row) else ""
        entries = []

        for code, col in debit_cols.items():
            amt = _safe_float(row[col]) if col < len(row) else 0
            if amt > 0:
                entries.append({
                    "direction": "debit",
                    "account_code": code,
                    "account_name": "",
                    "amount": amt,
                })

        for code, col in credit_cols.items():
            amt = _safe_float(row[col]) if col < len(row) else 0
            if amt > 0:
                entries.append({
                    "direction": "credit",
                    "account_code": code,
                    "account_name": "",
                    "amount": amt,
                })

        if entries:
            vouchers.append({
                "voucher_no": voucher_no,
                "voucher_date": _safe_str(row[date_col]) if date_col < len(row) else "",
                "description": _safe_str(row[desc_col]) if desc_col < len(row) else "",
                "entries": entries,
                "is_posted": True,
            })

    _logger.info("解析会计凭证(汇总格式): %d 笔凭证", len(vouchers))
    return vouchers


def _extract_account_code(header: str) -> str:
    """从列名中提取科目编码，如「借方金额(1002)」→「1002」"""
    import re
    match = re.search(r'\((\d{4})\)', header)
    if match:
        return match.group(1)
    return ""


def parse_trial_balance_sheet(ws) -> dict:
    """
    解析「试算平衡表」Sheet。

    输出格式：
      {
        "period": "2025-06",
        "opening_balance": {"1001": 50000, "1002": 3840000, ...},
        "closing_balance": {"1001": 50000, "1002": 3202545, ...}
      }
    """
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    if len(rows) < 2:
        return {}

    headers = [_safe_str(h) for h in rows[0]]
    col_map: dict[str, int] = {}
    for idx, h in enumerate(headers):
        for cn_key, en_key in TB_COLUMNS.items():
            if cn_key in h or en_key in h.lower():
                col_map[en_key] = idx

    if "account_code" not in col_map:
        _logger.warning("试算平衡表未检测到「科目编码」列")
        return {}

    opening: dict[str, float] = {}
    closing: dict[str, float] = {}

    for row in rows[1:]:
        if all(v is None or str(v).strip() == "" for v in row):
            continue

        code = _safe_str(row[col_map["account_code"]])
        if not code:
            continue

        if "opening_balance" in col_map:
            opening[code] = _safe_float(row[col_map["opening_balance"]])
        if "closing_balance" in col_map:
            closing[code] = _safe_float(row[col_map["closing_balance"]])

    result = {
        "opening_balance": opening,
        "closing_balance": closing,
    }
    _logger.info("解析试算平衡表: %d 个科目", len(closing) or len(opening))
    return result


def parse_financial_statements_sheet(ws) -> dict:
    """
    解析「财务报表」Sheet。

    期望格式：A列=项目名称，B列=金额

    输出格式：
      {
        "balance_sheet": {
          "total_assets": 19890733.55,
          "total_liabilities": 17142700.0,
          "items": {"流动资产": 10740996.12, "流动负债": 10628474.0, ...}
        },
        "income_statement": {
          "items": {"一、营业收入": 1754391.01, ...}
        }
      }
    """
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    if len(rows) < 2:
        return {}

    # 按行解析：项目名→金额
    items: dict[str, float] = {}
    for row in rows:
        if len(row) < 2:
            continue
        name = _safe_str(row[0])
        val = _safe_float(row[1])
        if name and val > 0:
            items[name] = val

    # 分类到 balance_sheet 和 income_statement
    bs_keys = {"资产总计", "负债总计", "流动资产", "非流动资产", "流动负债", "非流动负债", "所有者权益"}
    inc_keys = {"一、营业收入", "营业收入", "营业成本", "税金及附加", "销售费用", "管理费用", "财务费用",
                "营业利润", "所得税费用", "净利润", "二、营业利润", "三、净利润"}

    bs_items = {}
    inc_items = {}
    for k, v in items.items():
        if k in inc_keys or "收入" in k or "成本" in k or "费用" in k or "利润" in k or "税" in k:
            inc_items[k] = v
        else:
            bs_items[k] = v

    result = {
        "balance_sheet": {
            "total_assets": bs_items.get("资产总计", 0),
            "total_liabilities": bs_items.get("负债总计", 0),
            "total_equity": bs_items.get("所有者权益", 0),
            "items": bs_items,
        },
        "income_statement": {
            "items": inc_items,
        },
    }
    _logger.info("解析财务报表: BS %d项, IS %d项", len(bs_items), len(inc_items))
    return result


def parse_tax_ledger_sheet(ws) -> dict:
    """
    解析「税务台账」Sheet。

    期望格式：A列=税种，B列=项目，C列=金额

    输出格式：
      {
        "vat": {"output_tax": ..., "input_tax": ..., "net_payable": ..., "declared_revenue": ...},
        "corporate_income_tax": {"tax_payable": ...}
      }
    """
    rows = list(ws.iter_rows(min_row=1, values_only=True))
    if len(rows) < 2:
        return {}

    # 检测格式：是否有表头行
    items: dict[str, dict[str, float]] = {}
    current_tax_type: str | None = None

    for row in rows:
        if len(row) < 2:
            continue

        col0 = _safe_str(row[0])
        col1 = _safe_str(row[1]) if len(row) > 1 else ""

        # 检测税种行
        if "增值税" in col0 or "VAT" in col0.upper():
            current_tax_type = "vat"
            if current_tax_type not in items:
                items[current_tax_type] = {}
            continue
        if "企业所得税" in col0 or "所得税" in col0:
            current_tax_type = "corporate_income_tax"
            if current_tax_type not in items:
                items[current_tax_type] = {}
            continue

        # 检测项目-金额行
        if current_tax_type:
            val = _safe_float(row[1]) if len(row) > 1 else 0
            name = col0

            field_map = {
                "销项税额": "output_tax",
                "进项税额": "input_tax",
                "应纳税额": "net_payable",
                "申报收入": "declared_revenue",
                "应交所得税": "tax_payable",
                "应纳税所得额": "taxable_income",
            }
            for cn, en in field_map.items():
                if cn in name:
                    items[current_tax_type][en] = val
                    break
            else:
                # 未匹配的也保留
                items[current_tax_type][name] = val

    _logger.info("解析税务台账: %s", list(items.keys()))
    return items


def parse_excel(file_bytes: bytes, filename: str = "") -> ParseResult:
    """
    解析上传的 Excel 文件，返回合规校验器所需的标准数据结构。

    Args:
        file_bytes: Excel 文件的二进制内容
        filename: 原始文件名（用于日志）

    Returns:
        ParseResult: 包含解析后的数据或错误信息
    """
    result = ParseResult(success=False)
    errors: list[str] = []
    warnings: list[str] = []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        errors.append(f"无法打开 Excel 文件: {str(e)}")
        result.errors = errors
        return result

    sheet_names = [s.lower() for s in wb.sheetnames]

    # ── 解析会计凭证 ──
    voucher_sheet = None
    for s in wb.sheetnames:
        if "凭证" in s or "voucher" in s.lower():
            voucher_sheet = s
            break
    if voucher_sheet:
        try:
            result.data["monthly_vouchers"] = parse_vouchers_sheet(wb[voucher_sheet])
        except Exception as e:
            errors.append(f"会计凭证解析失败: {str(e)}")
            _logger.exception("会计凭证解析异常")
    else:
        warnings.append("未找到「会计凭证」Sheet")

    # ── 解析试算平衡表 ──
    tb_sheet = None
    for s in wb.sheetnames:
        if "试算" in s or "平衡" in s or "trial" in s.lower() or "tb" in s.lower():
            tb_sheet = s
            break
    if tb_sheet:
        try:
            result.data["trial_balance"] = parse_trial_balance_sheet(wb[tb_sheet])
        except Exception as e:
            errors.append(f"试算平衡表解析失败: {str(e)}")
            _logger.exception("试算平衡表解析异常")
    else:
        warnings.append("未找到「试算平衡表」Sheet")

    # ── 解析财务报表 ──
    fs_sheet = None
    for s in wb.sheetnames:
        if "报表" in s or "财务" in s or "financial" in s.lower() or "fs" in s.lower():
            fs_sheet = s
            break
    if fs_sheet:
        try:
            result.data["financial_statements"] = parse_financial_statements_sheet(wb[fs_sheet])
        except Exception as e:
            errors.append(f"财务报表解析失败: {str(e)}")
            _logger.exception("财务报表解析异常")
    else:
        warnings.append("未找到「财务报表」Sheet")

    # ── 解析税务台账 ──
    tax_sheet = None
    for s in wb.sheetnames:
        if "税务" in s or "税" in s or "tax" in s.lower():
            tax_sheet = s
            break
    if tax_sheet:
        try:
            result.data["tax_ledger"] = parse_tax_ledger_sheet(wb[tax_sheet])
        except Exception as e:
            errors.append(f"税务台账解析失败: {str(e)}")
            _logger.exception("税务台账解析异常")
    else:
        warnings.append("未找到「税务台账」Sheet")

    # ── 数据完整性校验 ──
    _validate_result(result, errors, warnings)

    result.success = len(errors) == 0
    result.errors = errors
    result.warnings = warnings
    return result


def _validate_result(result: ParseResult, errors: list[str], warnings: list[str]) -> None:
    """校验解析结果的数据完整性"""
    # 凭证
    vouchers = result.vouchers
    if not vouchers:
        errors.append("会计凭证数据为空，无法进行合规校验")

    # 试算平衡表
    tb = result.trial_balance
    if not tb.get("closing_balance"):
        errors.append("试算平衡表期末余额数据为空")
    required_tb_codes = ["1122", "2202", "1405"]  # checker 必须的科目
    closing = tb.get("closing_balance", {})
    for code in required_tb_codes:
        if code not in closing:
            warnings.append(f"试算平衡表缺少科目 {code}，相关规则将被跳过")

    # 财务报表
    fs = result.financial_statements
    bs = fs.get("balance_sheet", {}) if fs else {}
    inc = fs.get("income_statement", {}) if fs else {}

    if not bs.get("total_assets"):
        errors.append("财务报表缺少「资产总计」")
    if not bs.get("total_liabilities"):
        warnings.append("财务报表缺少「负债总计」")
    inc_items = inc.get("items", {})
    if not inc_items or "一、营业收入" not in inc_items:
        warnings.append("利润表缺少「一、营业收入」，增值税税负相关规则将被跳过")

    # 税务台账
    tax = result.tax_ledger
    if tax:
        vat = tax.get("vat", {})
        if not vat:
            warnings.append("税务台账缺少增值税数据")
        cit = tax.get("corporate_income_tax", {})
        if not cit:
            warnings.append("税务台账缺少企业所得税数据")
    else:
        warnings.append("税务台账数据为空，申报收入差异规则将被跳过")
