"""
文档上传与合规分析 API

POST /api/v1/enterprises/{id}/upload-documents    上传业务报表并自动解析校验
"""

import json
import logging
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db, success_response, error_response,
    require_admin_or_auditor, get_enterprise_or_403,
)
from app.models.remediation_task import RemediationTask, TaskStatus
from app.models.user import User
from app.core.document_parser import parse_excel, ParseResult
from app.core.compliance_checker import run_compliance_check
from app.core.compliance_adjustment import compute_compliance_adjusted_risk

router = APIRouter(tags=["文档上传"])
_logger = logging.getLogger(__name__)

# 支持的文件类型
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 数据库行业代码 → 中文名称映射
INDUSTRY_NAME_MAP = {
    "WHOLESALE_RETAIL": "批发零售",
    "MANUFACTURING": "制造",
    "CONSTRUCTION": "建筑",
    "E_COMMERCE": "电商",
    "CATERING": "餐饮服务",
}


@router.post("/enterprises/{enterprise_id}/upload-documents")
async def upload_documents(
    enterprise_id: UUID,
    file: UploadFile = File(..., description="Excel 报表文件（.xlsx/.xls）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_auditor),
):
    """
    上传业务报表 Excel 文件，自动解析并进行合规校验。

    流程：
      1. 校验文件类型和大小
      2. 调用文档解析引擎提取数据
      3. 运行合规校验，生成 findings
      4. 返回发现的不合规条目及关联任务的建议状态

    响应包含：
      - parse_result: 解析结果（成功/失败、警告）
      - findings: 合规校验发现的不合规条目
      - task_suggestions: 对已有合规整改任务的完成状态建议
    """
    ent_id = str(enterprise_id)

    # ── 1. 校验企业（租户隔离：企业必须属于当前用户租户） ──
    enterprise = await get_enterprise_or_403(ent_id, current_user, db)

    # ── 2. 校验文件类型 ──
    filename = file.filename or "unknown.xlsx"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return error_response(40010, f"不支持的文件类型: {ext}，仅支持 .xlsx / .xls")

    # ── 3. 校验文件大小 ──
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return error_response(40011, f"文件过大（{len(file_bytes) / 1024 / 1024:.1f}MB），上限 10MB")

    # ── 4. 调用文档解析引擎 ──
    _logger.info("开始解析上传文件: %s (%d bytes)", filename, len(file_bytes))
    parse_result = parse_excel(file_bytes, filename)

    parse_info = {
        "success": parse_result.success,
        "filename": filename,
        "errors": parse_result.errors,
        "warnings": parse_result.warnings,
        "data_summary": {
            "vouchers_count": len(parse_result.vouchers),
            "trial_balance_codes": len(parse_result.trial_balance.get("closing_balance", {})),
            "bs_items": len(parse_result.financial_statements.get("balance_sheet", {}).get("items", {})),
            "inc_items": len(parse_result.financial_statements.get("income_statement", {}).get("items", {})),
            "tax_types": list(parse_result.tax_ledger.keys()) if parse_result.tax_ledger else [],
        },
    }

    if not parse_result.success:
        return error_response(40012, "文档解析失败", data={"parse_result": parse_info})

    # ── 5. 运行合规校验 ──
    industry = INDUSTRY_NAME_MAP.get(str(enterprise.industry), "批发零售")
    annual_revenue = float(enterprise.revenue_annual or 0)

    findings = run_compliance_check(
        enterprise_name=enterprise.name,
        industry=industry,
        annual_revenue=annual_revenue,
        vouchers=parse_result.vouchers,
        trial_balance=parse_result.trial_balance,
        financial_statements=parse_result.financial_statements,
        tax_ledger=parse_result.tax_ledger,
    )

    # ── 6. 过滤已完成的合规任务对应的 findings ──
    resolved_keys: set[str] = set()
    completed_result = await db.execute(
        select(RemediationTask).where(
            RemediationTask.enterprise_id == ent_id,
            RemediationTask.status == TaskStatus.COMPLETED,
            RemediationTask.source == "compliance",
        )
    )
    for task in completed_result.scalars().all():
        if task.compliance_tags:
            for tag in task.compliance_tags:
                resolved_keys.add(tag)

    unresolved_findings = [f for f in findings if f["rule_key"] not in resolved_keys]

    # ── 7. 获取当前待处理的合规任务，生成完成建议 ──
    pending_result = await db.execute(
        select(RemediationTask).where(
            RemediationTask.enterprise_id == ent_id,
            RemediationTask.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            RemediationTask.source == "compliance",
        )
    )
    pending_tasks = pending_result.scalars().all()

    # 对每个待处理任务，检查其 compliance_tags 中的 rule_key 是否仍有未解决的 finding
    task_suggestions = []
    for task in pending_tasks:
        if not task.compliance_tags:
            continue
        # 该任务关联的 rule_keys 中，还有多少条未解决
        related_findings = [
            f for f in unresolved_findings
            if f["rule_key"] in task.compliance_tags
        ]
        task_suggestions.append({
            "task_id": str(task.id),
            "title": task.title,
            "status": task.status.value,
            "tags": task.compliance_tags,
            "unresolved_findings_count": len(related_findings),
            "suggested_action": "complete" if len(related_findings) == 0 else "keep_pending",
            "suggested_progress": 100 if len(related_findings) == 0 else None,
        })

    # ── 8. 自动判定新发现的不合规项，生成创建任务建议 ──
    new_finding_rules = [f["rule_key"] for f in unresolved_findings]
    existing_task_rules: set[str] = set()
    all_tasks_result = await db.execute(
        select(RemediationTask).where(
            RemediationTask.enterprise_id == ent_id,
            RemediationTask.source == "compliance",
        )
    )
    for t in all_tasks_result.scalars().all():
        if t.compliance_tags:
            for tag in t.compliance_tags:
                existing_task_rules.add(tag)

    # 需要新建任务的 rule_keys
    rules_needing_task = [r for r in new_finding_rules if r not in existing_task_rules]

    # ── 9. 合规调整后的风险评分 ──
    compliance_adj = None
    try:
        compliance_adj = await compute_compliance_adjusted_risk(db, ent_id)
    except Exception:
        pass

    return success_response({
        "enterprise_id": ent_id,
        "enterprise_name": enterprise.name,
        "parse_result": parse_info,
        "findings": {
            "total": len(unresolved_findings),
            "by_severity": {
                "high": len([f for f in unresolved_findings if f["severity"] == "high"]),
                "medium": len([f for f in unresolved_findings if f["severity"] == "medium"]),
                "low": len([f for f in unresolved_findings if f["severity"] == "low"]),
            },
            "items": unresolved_findings,
        },
        "task_suggestions": task_suggestions,
        "new_tasks_needed": rules_needing_task,
        "compliance_adjusted": compliance_adj,
    }, message=f"文档解析完成，合规校验发现 {len(unresolved_findings)} 条不合规条目")


@router.post("/enterprises/{enterprise_id}/upload-documents/confirm-task")
async def confirm_task_from_upload(
    enterprise_id: UUID,
    task_id: str = Form(..., description="要标记完成的整改任务ID"),
    action: str = Form(..., description="操作: complete / create"),
    new_finding_rules: str = Form(default="", description="逗号分隔的 rule_key 列表（action=create时必填）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_auditor),
):
    """
    确认上传解析后的任务操作：
    - action=complete: 将指定任务标记为已完成
    - action=create: 基于新发现的不合规项创建合规整改任务
    """
    ent_id = str(enterprise_id)

    # ── 租户隔离校验：企业必须属于当前用户租户，否则 403 ──
    await get_enterprise_or_403(ent_id, current_user, db)

    if action == "complete":
        # 将指定任务标记为已完成
        task_result = await db.execute(
            select(RemediationTask).where(
                RemediationTask.id == task_id,
                RemediationTask.enterprise_id == ent_id,
            )
        )
        task = task_result.scalar_one_or_none()
        if not task:
            return error_response(40013, f"任务不存在: {task_id}")

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.feedback_notes = "基于上传材料自动校验通过，所有关联合规项已验证完成"

        await db.commit()
        await db.refresh(task)

        _logger.info("上传确认: 任务 %s 已标记为完成", task_id)

        # 重新计算合规调整后的风险
        compliance_adj = None
        try:
            compliance_adj = await compute_compliance_adjusted_risk(db, ent_id)
        except Exception:
            pass

        return success_response({
            "task_id": task_id,
            "new_status": "completed",
            "compliance_adjusted": compliance_adj,
        }, message="任务已标记为完成")

    elif action == "create":
        # 创建新的合规整改任务
        rules = [r.strip() for r in new_finding_rules.split(",") if r.strip()]
        if not rules:
            return error_response(40014, "未指定要创建任务的合规项")

        from datetime import date
        db_task = RemediationTask(
            enterprise_id=ent_id,
            title=f"合规整改 - {len(rules)}项待处理",
            description=f"基于上传材料校验发现的不合规项，涉及规则: {', '.join(rules)}",
            priority="high" if len(rules) >= 3 else "medium",
            source="compliance",
            compliance_tags=rules,
            due_date=date.today(),
        )
        db.add(db_task)
        await db.commit()
        await db.refresh(db_task)

        _logger.info("上传确认: 新建合规任务 %s，关联 %d 条规则", db_task.id, len(rules))

        return success_response({
            "task_id": str(db_task.id),
            "title": db_task.title,
            "tags": rules,
        }, message=f"已创建合规整改任务，关联 {len(rules)} 条规则")

    else:
        return error_response(40015, f"不支持的操作: {action}，仅支持 complete / create")
