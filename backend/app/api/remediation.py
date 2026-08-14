"""
整改追踪 API

GET    /api/v1/enterprises/{id}/remediation-tasks    获取整改任务列表
POST   /api/v1/enterprises/{id}/remediation-tasks    创建整改任务
PUT    /api/v1/remediation-tasks/{id}                更新整改任务状态
GET    /api/v1/remediation-tasks/{id}                获取整改任务详情
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db, success_response, error_response,
    require_viewer, require_auditor, get_enterprise_or_403,
)
from app.core.risk_engine import assess_enterprise_risk
from app.core.four_flow_match import calculate_four_flow_match
from app.models.risk_assessment import RiskAssessment, AssessRiskLevel
from app.models.remediation_task import RemediationTask, TaskStatus
from app.models.user import User
from app.schemas.remediation import (
    RemediationTaskCreate, RemediationTaskUpdate,
    RemediationTaskResponse,
)
from app.schemas.risk_scan import RiskAssessmentResponse
from app.services.risk_service import RiskScanService
from app.core.compliance_adjustment import compute_compliance_adjusted_risk

logger = logging.getLogger("remediation_router")
router = APIRouter(tags=["整改追踪"])


# ══════════════════════════════════════════════════════
# 私有辅助：任务完成后触发风险重评
# ══════════════════════════════════════════════════════
async def _perform_risk_reassessment(
    task_id: UUID,
    enterprise_id: str,
    db: AsyncSession,
    tenant_id: str | None = None,
) -> dict | None:
    """在整改任务完成后，重新运行风险扫描并保存结果。
    
    返回 {"before": ..., "after": ...} 用于前后对比，
    失败时记录日志并返回 None。
    """
    try:
        # 1. 获取整改前的最近一次评估
        before_assessment = await RiskScanService.get_latest_assessment(
            db, enterprise_id
        )
        before_data = (
            RiskAssessmentResponse.model_validate(before_assessment).model_dump()
            if before_assessment else None
        )

        # 2. 加载企业数据
        ent, txs, invs, cts, decs = await RiskScanService.load_enterprise_data(
            db, enterprise_id, tenant_id
        )
        if not ent:
            logger.warning("风险重评失败 (task_id=%s): 企业不存在", task_id)
            return None

        # 3. 构建风险输入
        risk_input, ct_records, inv_records, bk_records = \
            RiskScanService.build_risk_input(ent, txs, invs, cts, decs)

        # 4. 补充财务数据
        await RiskScanService.enrich_with_financials(db, enterprise_id, risk_input)

        # 5. 执行风险扫描（B1：读取参数配置，未配置回退引擎默认值）
        from app.core.risk_config import get_risk_config
        config = await get_risk_config(db)
        risk_result = assess_enterprise_risk(
            risk_input,
            contracts=ct_records,
            invoices=inv_records,
            bank_transactions=bk_records,
            has_tax_preference=ent.is_small_micro or ent.is_high_tech,
            config=config,
        )

        # 6. 四流匹配
        ffm_result = calculate_four_flow_match(ct_records, inv_records, bk_records)

        # 7. 持久化（复用 RiskScanService）
        assessment = await RiskScanService.save_assessment(
            db, enterprise_id, risk_result, ffm_result,
            risk_input=risk_input, transactions=txs,
        )

        # 7.5 记录评分轨迹（整改完成 → 前后演化证据链，B3）
        try:
            await RiskScanService.record_score_trajectory(
                db, enterprise_id,
                after_score=float(assessment.overall_risk_score),
                after_level=str(assessment.overall_risk_level.value),
                before_score=(
                    float(before_assessment.overall_risk_score)
                    if before_assessment else None
                ),
                before_level=(
                    str(before_assessment.overall_risk_level.value)
                    if before_assessment else None
                ),
                changed_by="remediation",
                reason=f"整改任务完成（{task_id}），触发风险重评估",
            )
        except Exception:
            logger.exception("评分轨迹写入失败 (task_id=%s)", task_id)

        after_data = RiskAssessmentResponse.model_validate(assessment).model_dump()

        # ── 合规调整：注入联动风险评分 ──
        try:
            compliance_adj = await compute_compliance_adjusted_risk(
                db, enterprise_id,
                base_score=float(assessment.overall_risk_score or 0),
            )
            for data_section in [before_data, after_data]:
                if data_section:
                    data_section["compliance_adjusted"] = compliance_adj
        except Exception:
            pass

        logger.info("风险重评完成 (task_id=%s, enterprise=%s)", task_id, enterprise_id)
        return {"before": before_data, "after": after_data}

    except (ValueError, LookupError) as e:
        logger.warning("风险重评失败 (task_id=%s): %s", task_id, e)
    except Exception:
        logger.exception("风险重评异常 (task_id=%s)", task_id)

    return None


# ══════════════════════════════════════════════════════
# API 端点
# ══════════════════════════════════════════════════════

@router.get("/enterprises/{enterprise_id}/remediation-tasks")
async def list_remediation_tasks(
    enterprise_id: UUID,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """获取整改任务列表"""
    # 租户隔离校验
    await get_enterprise_or_403(str(enterprise_id), current_user, db)

    query = select(RemediationTask).where(
        RemediationTask.enterprise_id == str(enterprise_id)
    ).order_by(RemediationTask.created_at.desc())

    if status:
        query = query.where(RemediationTask.status == status)
    if priority:
        query = query.where(RemediationTask.priority == priority)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return success_response({
        "tasks": [
            RemediationTaskResponse.model_validate(t).model_dump()
            for t in tasks
        ],
        "total": total,
    })


@router.post("/enterprises/{enterprise_id}/remediation-tasks", status_code=201)
async def create_remediation_task(
    enterprise_id: UUID,
    task: RemediationTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auditor),
):
    """创建整改任务"""
    # 租户隔离校验
    await get_enterprise_or_403(str(enterprise_id), current_user, db)

    db_task = RemediationTask(
        enterprise_id=str(enterprise_id),
        risk_assessment_id=task.risk_assessment_id,
        title=task.title,
        description=task.description,
        priority=task.priority,
        due_date=task.due_date,
        source=task.source or "manual",
        compliance_tags=task.compliance_tags,
    )
    db.add(db_task)
    await db.flush()
    await db.refresh(db_task)

    return success_response(
        RemediationTaskResponse.model_validate(db_task).model_dump(),
        message="整改任务创建成功",
    )


@router.put("/remediation-tasks/{task_id}")
async def update_remediation_task(
    task_id: UUID,
    update: RemediationTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auditor),
):
    """更新整改任务状态，完成任务时自动触发风险重评"""
    result = await db.execute(
        select(RemediationTask).where(RemediationTask.id == str(task_id))
    )
    task = result.scalar_one_or_none()

    if not task:
        return error_response(40001, f"整改任务不存在: {task_id}")

    # 租户隔离校验：任务所属企业必须属于当前用户租户
    await get_enterprise_or_403(str(task.enterprise_id), current_user, db)

    update_data = update.model_dump(exclude_unset=True)
    old_status = str(task.status) if task.status else "unknown"
    # 用户是否显式要求切换状态
    explicit_status_change = "status" in update_data

    for key, value in update_data.items():
        setattr(task, key, value)

    # ── 智能状态联动 ──
    # 如果用户主动将任务重置为 pending（如已完成 → 待处理），清零进度
    if task.status == TaskStatus.PENDING and explicit_status_change:
        task.progress = Decimal("0")

    # 进度 > 0 且当前为 pending → 自动转为 in_progress
    if (
        task.status == TaskStatus.PENDING
        and task.progress is not None
        and float(task.progress) > 0
    ):
        task.status = TaskStatus.IN_PROGRESS

    # 进度达到 100% → 自动转为 completed
    if (
        task.status != TaskStatus.COMPLETED
        and task.progress is not None
        and float(task.progress) >= 100
    ):
        task.status = TaskStatus.COMPLETED

    # 状态变为已完成时，自动设置完成时间
    new_status = str(task.status) if task.status else "unknown"
    trigger_re_scan = (
        old_status != TaskStatus.COMPLETED.value
        and new_status == TaskStatus.COMPLETED.value
    )
    if trigger_re_scan and not task.completed_at:
        task.completed_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(task)

    # ── 触发风险重评 ──
    comparison_data = None
    if trigger_re_scan:
        comparison_data = await _perform_risk_reassessment(
            task_id, str(task.enterprise_id), db, current_user.tenant_id
        )

    response = RemediationTaskResponse.model_validate(task).model_dump()
    if comparison_data:
        response["comparison"] = comparison_data
        response["message"] = "任务完成，风险已重新评估"

    return success_response(response)


@router.get("/remediation-tasks/{task_id}")
async def get_remediation_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """获取整改任务详情"""
    result = await db.execute(
        select(RemediationTask).where(RemediationTask.id == str(task_id))
    )
    task = result.scalar_one_or_none()

    if not task:
        return error_response(40001, f"整改任务不存在: {task_id}")

    # 租户隔离校验：任务所属企业必须属于当前用户租户
    await get_enterprise_or_403(str(task.enterprise_id), current_user, db)

    return success_response(
        RemediationTaskResponse.model_validate(task).model_dump()
    )
