"""
报告生成 API

POST /api/v1/enterprises/{id}/reports/generate          生成风险评估报告
GET  /api/v1/enterprises/{id}/reports                   获取报告列表
GET  /api/v1/reports/{id}                               获取报告详情
GET  /api/v1/enterprises/{id}/reports/download          下载报告（PDF）
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, success_response, error_response, require_viewer, require_auditor, get_current_tenant_id
from app.models.enterprise import Enterprise
from app.models.risk_assessment import RiskAssessment
from app.models.user import User
from app.schemas.reports import ReportGenerateRequest
from app.core.compliance_adjustment import compute_compliance_adjusted_risk
from app.core.four_flow_match import (
    GOODS_FLOW_DISCLAIMER,
    GOODS_FLOW_METHOD_INVOICE_TEXT_PROXY,
)
from app.core.pdf_generator import generate_report_pdf

router = APIRouter(tags=["报告生成"])


async def _build_report_content(
    enterprise_id: str,
    request: ReportGenerateRequest,
    db: AsyncSession,
    tenant_id: str,
) -> dict:
    """构建报告内容（内部函数，供 generate_report 和 list_reports 共用）"""
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        raise ValueError(f"企业不存在或无权访问: {enterprise_id}")

    # 获取最新风险评估
    risk_result = await db.execute(
        select(RiskAssessment).where(
            RiskAssessment.enterprise_id == enterprise_id
        ).order_by(RiskAssessment.assessment_date.desc()).limit(1)
    )
    latest_risk = risk_result.scalar_one_or_none()

    report_content = {
        "enterprise": {
            "id": str(enterprise.id),
            "name": enterprise.name,
            "industry": str(enterprise.industry),
            "revenue_annual": float(enterprise.revenue_annual or 0),
            "employee_count": enterprise.employee_count,
        },
        "risk_assessment": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "本报告基于模拟数据生成，仅供演示参考，不构成任何税务或法律建议。",
    }

    if latest_risk:
        report_content["risk_assessment"] = {
            "id": str(latest_risk.id),
            "level": latest_risk.overall_risk_level.value if latest_risk.overall_risk_level else "low",
            "score": float(latest_risk.overall_risk_score),
            "four_flow_match": float(latest_risk.four_flow_match_score),
            "private_card_ratio": float(latest_risk.private_card_ratio),
            "cost_deviation": float(latest_risk.cost_deviation),
            "details": latest_risk.risk_details or {},
            "recommendations": latest_risk.recommendations or {},
            "date": latest_risk.assessment_date.isoformat()
                if latest_risk.assessment_date else None,
        }
        # 货物流校验口径披露：优先取本次评估的技术摘要快照，缺失时按代理校验兜底
        risk_details = latest_risk.risk_details or {}
        goods_flow = (risk_details.get("technical_summary") or {}).get("goods_flow") or {}
        report_content["goods_flow"] = {
            "method": goods_flow.get("method", GOODS_FLOW_METHOD_INVOICE_TEXT_PROXY),
            "is_proxy_verification": bool(goods_flow.get("is_proxy_verification", True)),
            "disclaimer": goods_flow.get("disclaimer", GOODS_FLOW_DISCLAIMER),
        }

    risk_level_value = latest_risk.overall_risk_level.value if latest_risk and latest_risk.overall_risk_level else "low"

    return {
        "id": str(uuid4()),
        "enterprise_id": str(enterprise_id),
        "title": f"{enterprise.name} - 财税合规风险评估报告",
        "report_type": "comprehensive",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "content": report_content,
        "content_summary": {
            "risk_level": risk_level_value,
        },
    }


@router.post("/enterprises/{enterprise_id}/reports/generate")
async def generate_report(
    enterprise_id: str,
    request: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_auditor),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """生成风险评估报告"""
    try:
        report = await _build_report_content(enterprise_id, request, db, tenant_id)

        # ── 合规调整：显式双状态，杜绝 adjusted_level + original_score 交叉绑定 ──
        # 全项目统一口径（审计结论落地）：
        #   当前状态视图 = adjusted_score + adjusted_level 成对展示；
        #   历史/审计视图 = original_score + original_level 成对展示（快照不可变）。
        try:
            base_score = None
            risk_assessment = report.get("content", {}).get("risk_assessment")
            if risk_assessment and isinstance(risk_assessment, dict):
                base_score = risk_assessment.get("score")

            compliance_adj = await compute_compliance_adjusted_risk(
                db, enterprise_id,
                base_score=base_score,
            )
            adjusted_level = compliance_adj["adjusted_level"]

            # ① risk_assessment 保持原始快照（score+level 成对，审计留痕），不再覆盖
            # ② 整改后状态独立成节（adjusted_score+adjusted_level 成对 + 降幅/整改状态）
            report["content"]["compliance_adjusted_risk"] = compliance_adj
            # ③ 摘要（当前状态视图）= 调整后等级
            report["content_summary"]["risk_level"] = adjusted_level
        except Exception:
            pass

        return success_response(report, message="报告生成成功")
    except ValueError as e:
        return error_response(40001, str(e))


@router.get("/enterprises/{enterprise_id}/reports")
async def list_reports(
    enterprise_id: str,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取报告列表（简化：返回最新生成结果）"""
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == enterprise_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    # 简化实现：利用内部函数生成报告
    try:
        report_data = await _build_report_content(enterprise_id, ReportGenerateRequest(), db, tenant_id)
    except ValueError as e:
        return error_response(40001, str(e))
    return success_response({
        "reports": [report_data],
        "total": 1,
    })


@router.get("/reports/{report_id}")
async def get_report_detail(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
):
    """获取报告详情（简化实现）"""
    return success_response(
        {"id": str(report_id), "message": "报告详情请通过 generate 接口获取"},
        message="原型阶段：报告未持久化，请重新生成",
    )


@router.get("/enterprises/{enterprise_id}/reports/download")
async def download_report(
    enterprise_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """下载 PDF 格式的风险评估报告"""
    try:
        request = ReportGenerateRequest()
        report_data = await _build_report_content(enterprise_id, request, db, tenant_id)
        report_content = report_data.get("content", {})

        pdf_bytes = bytes(generate_report_pdf(report_content))

        ent_name = report_content.get("enterprise", {}).get("name", "report")
        filename = f"{ent_name}-财税合规风险评估报告.pdf".encode("utf-8").decode("latin-1", errors="replace")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            },
        )
    except ValueError as e:
        import traceback, logging
        logging.getLogger("app.main").error(f"ValueError: {e}\n{traceback.format_exc()}")
        return error_response(40001, str(e))
    except Exception as e:
        import traceback, logging
        logging.getLogger("app.main").error(f"Ex: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return error_response(50000, f"{type(e).__name__}: {str(e)[:150]}")
