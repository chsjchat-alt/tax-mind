"""
SSF 博弈状态分析 API

GET  /api/v1/ssf/enterprises/{id}       获取单企业SSF博弈状态
GET  /api/v1/ssf/summary                获取所有企业SSF坐标摘要
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, success_response, error_response, require_viewer, get_current_tenant_id
from app.models.enterprise import Enterprise
from app.models.user import User
from app.core.ssf_analyzer import (
    analyze_ssf_state,
    analyze_all_enterprises_ssf,
    SSFState,
)

router = APIRouter(prefix="/ssf", tags=["SSF博弈分析"])


def _state_to_dict(s: SSFState) -> dict:
    """将 SSFState 序列化为字典"""
    return {
        "enterprise_id": s.enterprise_id,
        "enterprise_name": s.enterprise_name,
        "power_coord": s.power_coord,
        "trust_coord": s.trust_coord,
        "quadrant": s.quadrant,
        "quadrant_name": s.quadrant_name,
        "quadrant_subtitle": s.quadrant_subtitle,
        "quadrant_color": s.quadrant_color,
        "quadrant_icon": s.quadrant_icon,
        "npt_mix": s.npt_mix,
        "primary_strategy": s.primary_strategy,
        "strategy_brief": s.strategy_brief,
        "target_direction": s.target_direction,
        "power_source": s.power_source,
        "trust_source": s.trust_source,
        "adjusted_risk_score": s.adjusted_risk_score,
        "risk_trend": s.risk_trend,
        "previous_quadrant": s.previous_quadrant,
        "movement_description": s.movement_description,
    }


@router.get("/enterprises/{enterprise_id}")
async def get_enterprise_ssf(
    enterprise_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """
    获取单个企业的 SSF 博弈状态分析。

    返回：
      - power_coord / trust_coord：二维坐标 (0-100)
      - quadrant：当前象限 (I/II/III/IV)
      - npt_mix：NPT 干预策略配比
      - primary_strategy：主导策略
      - history：历史轨迹点
    """
    ent_id = str(enterprise_id)

    result = await db.execute(
        select(Enterprise).where(
            Enterprise.id == ent_id,
            Enterprise.tenant_id == tenant_id,
        )
    )
    enterprise = result.scalar_one_or_none()
    if not enterprise:
        return error_response(40001, f"企业不存在或无权访问: {enterprise_id}")

    try:
        ssf_result = await analyze_ssf_state(db, ent_id, enterprise.name)
    except Exception as e:
        return error_response(50000, f"SSF 分析失败: {str(e)}")

    history_dicts = [
        {"date": hp.date, "power_coord": hp.power_coord, "trust_coord": hp.trust_coord,
         "quadrant": hp.quadrant, "event": hp.event}
        for hp in ssf_result.history
    ]

    return success_response({
        "current_state": _state_to_dict(ssf_result.current_state),
        "history": history_dicts,
    })


@router.get("/summary")
async def get_all_enterprises_ssf_summary(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_viewer),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """获取当前租户所有企业的 SSF 坐标摘要（用于散点图对比）。"""
    result = await db.execute(
        select(Enterprise).where(
            Enterprise.tenant_id == tenant_id,
        ).order_by(Enterprise.created_at.desc()).limit(20)
    )
    enterprises = result.scalars().all()
    summaries = [{"id": e.id, "name": e.name} for e in enterprises]

    try:
        points = await analyze_all_enterprises_ssf(db, summaries)
    except Exception as e:
        return error_response(50000, f"SSF 批量分析失败: {str(e)}")

    quadrant_counts = {"I": 0, "II": 0, "III": 0, "IV": 0}
    for p in points:
        q = p.get("quadrant", "I")
        if q in quadrant_counts:
            quadrant_counts[q] += 1

    return success_response({
        "enterprises": points,
        "quadrant_distribution": quadrant_counts,
        "total": len(points),
    })
