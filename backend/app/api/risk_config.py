"""
参数配置 API（B1 参数配置化）

GET /api/v1/risk-config    查看全部评分参数（含权威来源，viewer+）
PUT /api/v1/risk-config    批量更新评分参数（admin，变更后自动失效扫描缓存）
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.api.deps import (
    get_db, success_response, error_response,
    require_viewer, require_admin,
)
from app.core.risk_config import (
    DEFAULT_RISK_CONFIG, get_risk_config, upsert_risk_config,
)
from app.models.user import User

router = APIRouter(tags=["参数配置"])


@router.get("/risk-config")
async def list_risk_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
):
    """查看全部评分参数配置（含默认值元信息与权威来源）"""
    config = await get_risk_config(db)
    items = []
    for key in DEFAULT_RISK_CONFIG:
        meta = DEFAULT_RISK_CONFIG[key]
        items.append({
            "config_key": key,
            "config_value": config.get(key),
            "config_type": meta.get("type", "json"),
            "description": meta.get("description", ""),
            "source": meta.get("source", ""),
        })
    return success_response({"items": items, "total": len(items)})


@router.put("/risk-config")
async def update_risk_config(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """批量更新评分参数（仅接受已定义的配置键，变更后失效全部扫描缓存）"""
    unknown = [k for k in payload if k not in DEFAULT_RISK_CONFIG]
    if unknown:
        return error_response(40001, f"未知配置键: {unknown}")

    applied = await upsert_risk_config(
        db, payload, updated_by=str(current_user.id)
    )
    return success_response({"updated": applied, "count": len(applied)})
