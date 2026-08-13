"""
安全响应头配置

等保 2.0 / OWASP 安全基线：
  - Content-Security-Policy（无 unsafe-inline，开发模式自动放宽）
  - 禁用 MIME 嗅探：X-Content-Type-Options: nosniff
  - 引用策略：Referrer-Policy: strict-origin-when-cross-origin
  - 权限策略：Permissions-Policy 最小化
  - X-Frame-Options + HSTS 由生产 Nginx 统一管理
"""
from fastapi import Response

from app.config import get_settings


# ── 生产环境 CSP（严格） ────────────────────────────────────
# 注意：style-src 保留 'unsafe-inline'——Ant Design 5 采用 CSS-in-JS
# 运行时注入 <style> 标签，SPA 场景无法抽取，不放开会白屏。
# script-src 保持严格（'unsafe-inline' 才是 XSS 主要突破口）。
_CSP_PRODUCTION = (
    "default-src 'self'; "
    "script-src 'self' cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
    "img-src 'self' data:; "
    "font-src 'self' fonts.gstatic.com; "
    "connect-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)

# ── 开发环境 CSP（宽松 — 允许 CDN + blob worker）────────────
_CSP_DEVELOPMENT = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com blob:; "
    "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net unpkg.com fonts.googleapis.com; "
    "img-src 'self' data: https:; "
    "font-src 'self' fonts.gstatic.com data:; "
    "connect-src 'self' https:; "
    "worker-src 'self' blob:; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)

NON_CSP_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), "
        "payment=(), usb=(), bluetooth=()"
    ),
}


def apply_security_headers(response: Response) -> None:
    """将安全响应头注入到 FastAPI Response。

    开发模式(DEBUG=true)：使用宽松 CSP，允许 CDN + unsafe-inline
    生产模式(DEBUG=false)：使用严格 CSP
    """
    settings = get_settings()

    # 非 CSP 头始终应用
    for header_name, header_value in NON_CSP_HEADERS.items():
        if header_name not in response.headers:
            response.headers[header_name] = header_value

    # CSP 根据环境选择
    if "Content-Security-Policy" not in response.headers:
        csp_value = _CSP_DEVELOPMENT if settings.debug else _CSP_PRODUCTION
        response.headers["Content-Security-Policy"] = csp_value
