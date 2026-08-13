"""
「税智·心判」FastAPI 应用入口
"""
import asyncio
import json
import time
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.utils.response import success_response, error_response
from app.utils.pii import sanitize_response
from app.core.security import decode_token
from app.core.security_headers import apply_security_headers

settings = get_settings()

# React 构建产物目录（仅单容器 / Railway 部署时存在）
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUDIT_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}

# 创建 FastAPI 实例
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="中小民企老板财税合规决策支持系统",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

async def _write_audit_log(log_entry: dict) -> None:
    """异步写入一条审计日志"""
    import logging as _logging
    _audit_logger = _logging.getLogger("audit")
    try:
        from app.database import AsyncSessionLocal
        from app.models.audit_log import AuditLog

        async with AsyncSessionLocal() as db:
            db.add(AuditLog(**log_entry))
            await db.commit()
    except Exception as e:
        _audit_logger.error(f"Audit log write failed: {e}")


# 请求日志 + 审计日志 + 安全头 + 请求体大小限制中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # ── 请求体大小限制（10 MB）──
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:
        return JSONResponse(
            status_code=413,
            content={"code": 40002, "message": "请求体过大，上限 10MB", "data": None},
        )

    start = time.perf_counter()
    path = request.url.path

    # ── 审计：提取 JWT 信息 ──
    jwt_info = {"sub": None, "username": None, "tenant_id": None}
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            payload = decode_token(auth_header[7:])
            jwt_info = {
                "sub": payload.get("sub"),
                "username": payload.get("username"),
                "tenant_id": payload.get("tenant_id"),
            }
        except Exception:
            pass

    # ── 审计：包装 receive 以缓存请求体（不消耗下游读取）──
    should_audit = path not in AUDIT_SKIP_PATHS and not path.startswith("/docs") and not path.startswith("/redoc")
    body_chunks: list[bytes] = []
    if should_audit and request.method in ("POST", "PUT", "PATCH"):
        _original_receive = request.receive

        async def _wrapped_receive():
            msg = await _original_receive()
            if msg.get("type") == "http.request":
                body_chunks.append(msg.get("body", b""))
            return msg

        request._receive = _wrapped_receive  # type: ignore[attr-defined]

    # ── 执行请求 ──
    response = await call_next(request)
    duration = time.perf_counter() - start

    # ── 安全响应头 ──
    apply_security_headers(response)

    # ── 控制台日志 ──
    logger.info(
        f"{request.method} {path} "
        f"status={response.status_code} "
        f"duration={duration:.3f}s"
    )

    # ── 审计：提取请求体并脱敏 ──
    request_body: str | None = None
    if body_chunks:
        raw_body = b"".join(body_chunks).decode("utf-8", errors="replace")[:10240]
        if raw_body:
            try:
                body_data = json.loads(raw_body)
                body_data = sanitize_response(body_data)
                request_body = json.dumps(body_data, ensure_ascii=False)[:10240]
            except Exception:
                request_body = "[REDACTED]"

    # ── 审计：提取响应信息并异步写入 ──
    if should_audit:
        business_code = None
        response_summary = None

        # 读取响应体（非流式响应）
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type and not isinstance(response, StreamingResponse):
            try:
                body_str = getattr(response, "body", b"")
                if isinstance(body_str, str):
                    body_str = body_str.encode("utf-8")
                if body_str:
                    data = json.loads(body_str)
                    business_code = data.get("code")
                    sanitized = sanitize_response(data)
                    response_summary = json.dumps(sanitized, ensure_ascii=False)[:1024]
            except Exception:
                pass

        log_entry = {
            "user_id": jwt_info["sub"],
            "username": jwt_info["username"],
            "tenant_id": jwt_info["tenant_id"],
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "business_code": business_code,
            "duration_ms": int(duration * 1000),
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent", "")[:500],
            "request_body": request_body,
            "response_summary": response_summary,
        }
        asyncio.create_task(_write_audit_log(log_entry))

    return response


# 统一异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=error_response(50000, "服务器内部错误"),
    )


# 健康检查
@app.get("/health")
async def health_check():
    return success_response({"status": "ok", "version": settings.app_version})


# 根路径欢迎页（单容器部署时返回 React 前端，否则返回静态欢迎页）
@app.get("/")
async def root():
    index_file = _FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{settings.app_name}</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#0f172a;color:#e2e8f0;margin:0">
<div style="background:#1e293b;border-radius:12px;padding:48px;text-align:center;box-shadow:0 25px 50px -12px rgba(0,0,0,0.5);max-width:480px;width:90%%">
<h1 style="font-size:2rem;color:#f8fafc;margin:0 0 8px">{settings.app_name}</h1>
<p style="font-size:.875rem;color:#64748b;margin:0 0 32px">v{settings.app_version}</p>
<div style="display:flex;flex-direction:column;gap:12px">
<a href="/docs" style="display:block;padding:12px 20px;background:#334155;color:#e2e8f0;text-decoration:none;border-radius:8px">Swagger API 文档</a>
<a href="/redoc" style="display:block;padding:12px 20px;background:#334155;color:#e2e8f0;text-decoration:none;border-radius:8px">ReDoc API 文档</a>
<a href="/openapi.json" style="display:block;padding:12px 20px;background:#334155;color:#e2e8f0;text-decoration:none;border-radius:8px">OpenAPI Schema</a>
<a href="/health" style="display:block;padding:12px 20px;background:#334155;color:#e2e8f0;text-decoration:none;border-radius:8px">健康检查</a>
</div></div></body></html>""")


# 注册路由：各业务域 router 已在 app/api/__init__.py 统一聚合
from app.api import api_router

app.include_router(api_router, prefix="/api/v1")


# ── 前端静态托管（单容器 / Railway 部署）──────────────
# 仅在 React 构建产物（frontend/dist）存在时启用；
# 开发环境由 Vite 提供前端、compose 部署由 Nginx 提供，均不受影响。
if _FRONTEND_DIST.is_dir():
    _assets_dir = _FRONTEND_DIST / "assets"
    if _assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=_assets_dir),
            name="frontend-assets",
        )

    @app.exception_handler(404)
    async def _spa_fallback(request: Request, exc: Exception):
        """React Router SPA fallback：非 API 路径统一返回 index.html"""
        # API/文档/系统路径保持标准 404，避免被前端路由吞掉
        path = request.url.path
        if (
            path.startswith("/api")
            or path.startswith("/docs")
            or path.startswith("/redoc")
            or path.startswith("/openapi.json")
            or path == "/favicon.ico"
            or path == "/health"
        ):
            return JSONResponse(
                status_code=404,
                content=error_response(40400, "资源不存在"),
            )
        index_file = _FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse(
            status_code=404,
            content=error_response(40400, "资源不存在"),
        )



@app.on_event("startup")
async def startup():
    logger.info(f"{settings.app_name} v{settings.app_version} 启动中...")
    # 开发/SQLite 环境自动建表；生产 PostgreSQL 应通过 `alembic upgrade head` 管理 schema
    if settings.debug or "sqlite" in settings.database_url:
        from app.database import init_db
        await init_db()
    logger.info(f"{settings.app_name} 启动完成")
