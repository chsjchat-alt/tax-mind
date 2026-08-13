"""
合规校验 API

GET  /api/v1/enterprises/{enterprise_id}/compliance-check  运行合规校验
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, success_response, error_response, require_auditor, get_current_tenant_id
from app.models.enterprise import Enterprise
from app.models.remediation_task import RemediationTask, TaskStatus
from app.models.user import User
from app.core.compliance_checker import run_compliance_check

router = APIRouter(tags=["合规校验"])
_logger = logging.getLogger(__name__)

# 数据库行业代码 → 中文名称映射
INDUSTRY_NAME_MAP = {
    "WHOLESALE_RETAIL": "批发零售",
    "MANUFACTURING": "制造",
    "CONSTRUCTION": "建筑",
    "E_COMMERCE": "电商",
    "CATERING": "餐饮服务",
}


@router.get("/enterprises/{enterprise_id}/compliance-check")
async def run_enterprise_compliance_check(
    enterprise_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_auditor),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    对企业最新生成的财务数据运行全量合规校验。

    返回所有不合规发现条目（含严重级别、分类、描述、建议整改措施）。
    """
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 加载已生成的财务数据（从 JSON 文件）
    data_dir = Path(__file__).parent.parent.parent / "generated_financial_data"
    enterprise_name = enterprise.name
    matched_file = None

    for fpath in data_dir.glob("*.json"):
        if enterprise_name in fpath.name:
            matched_file = fpath
            break

    if not matched_file:
        return error_response(40002, f"未找到企业 {enterprise_name} 的财务数据，请先运行 generate_financial_data.py")

    try:
        with open(matched_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return error_response(40003, f"财务数据加载失败: {str(e)}")

    findings = run_compliance_check(
        enterprise_name=enterprise.name,
        industry=INDUSTRY_NAME_MAP.get(str(enterprise.industry), "批发零售"),
        annual_revenue=float(enterprise.revenue_annual or 0),
        vouchers=data.get("monthly_vouchers", []),
        trial_balance=data.get("trial_balance", {}),
        financial_statements=data.get("financial_statements", {}),
        tax_ledger=data.get("tax_ledger", {}),
    )

    # ── 已完成合规整改的任务会"消除"对应不合规条目 ──
    resolved_keys: set[str] = set()
    completed_result = await db.execute(
        select(RemediationTask).where(
            RemediationTask.enterprise_id == enterprise_id,
            RemediationTask.status == TaskStatus.COMPLETED,
            RemediationTask.source == "compliance",
        )
    )
    for task in completed_result.scalars().all():
        if task.compliance_tags:
            for tag in task.compliance_tags:
                resolved_keys.add(tag)

    original_count = len(findings)
    findings = [f for f in findings if f["rule_key"] not in resolved_keys]
    resolved_count = original_count - len(findings)
    if resolved_count > 0:
        _logger.info(
            "合规复验：%s 已完成 %d 条整改，过滤 %d 条已解决发现",
            enterprise.name, len(resolved_keys), resolved_count,
        )

    return success_response({
        "enterprise_id": enterprise_id,
        "enterprise_name": enterprise.name,
        "findings_count": len(findings),
        "by_severity": {
            "high": len([f for f in findings if f["severity"] == "high"]),
            "medium": len([f for f in findings if f["severity"] == "medium"]),
            "low": len([f for f in findings if f["severity"] == "low"]),
        },
        "by_category": _group_by(findings, "category"),
        "findings": findings,
    }, message=f"合规校验完成，发现 {len(findings)} 条不合规条目")


def _group_by(items: list[dict], key: str) -> dict:
    """辅助：按字段分组计数"""
    result: dict[str, int] = {}
    for item in items:
        val = item.get(key, "unknown")
        result[val] = result.get(val, 0) + 1
    return result
