"""
API 路由包

统一聚合各业务域 router，应用入口只需挂载一次：
    from app.api import api_router
    app.include_router(api_router, prefix="/api/v1")
"""
from fastapi import APIRouter

from app.api.enterprises import router as enterprise_router
from app.api.data_ingestion import router as data_router
from app.api.risk_scan import router as risk_router
from app.api.simulation import router as simulation_router
from app.api.compliance import router as compliance_router
from app.api.compliance_check import router as compliance_check_router
from app.api.remediation import router as remediation_router
from app.api.reports import router as reports_router
from app.api.ai_assistant import router as ai_router
from app.api.auth import router as auth_router
from app.api.upload import router as upload_router
from app.api.risk_config import router as risk_config_router
from app.api.deemed_deduction import router as deemed_deduction_router

# 聚合根路由：新增业务域时只需在此追加一行
api_router = APIRouter()
for _router in (
    auth_router,
    enterprise_router,
    data_router,
    risk_router,
    simulation_router,
    compliance_router,
    compliance_check_router,
    remediation_router,
    reports_router,
    upload_router,
    risk_config_router,
    deemed_deduction_router,
    ai_router,
):
    api_router.include_router(_router)

__all__ = ["api_router"]
