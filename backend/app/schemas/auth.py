"""
认证相关 Pydantic Schema
"""
from pydantic import BaseModel, EmailStr, field_validator
import re


class LoginRequest(BaseModel):
    """OAuth2 密码流登录请求"""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """用户注册请求（角色由服务端强制设为 viewer，防止提权）"""
    username: str
    password: str
    tenant_slug: str
    email: EmailStr | None = None
    full_name: str | None = None
    enterprise_id: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]{3,50}$", v):
            raise ValueError("用户名仅允许字母、数字、下划线，长度 3-50")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("密码长度至少 10 位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码需包含大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码需包含小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含数字")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_+-]", v):
            raise ValueError("密码需包含特殊字符")
        return v


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """用户信息响应"""
    id: str
    username: str
    email: str | None = None
    full_name: str | None = None
    enterprise_id: str | None = None
    tenant_id: str
    role: str
    is_active: bool
