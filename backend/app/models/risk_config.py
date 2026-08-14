"""风险引擎参数配置表 (risk_config)

B1 参数配置化（PDCA 闭环底座）：
  - W（权重）/ S（严重度倍数）/ P（概率）/ C（内控）/ R（修复加分）/ Q（法定信用扣分）
    等全部评分参数统一收口到本表，引擎从配置读取，未配置项回退代码内权威默认值。
  - 每个参数记录权威来源（source），满足「参数信息来源于官方权威渠道、可多源互证」。
"""
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, String, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RiskConfig(Base):
    __tablename__ = "risk_config"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    config_key: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False,
        comment="配置键（见 app.core.risk_config.DEFAULT_RISK_CONFIG）",
    )
    config_value: Mapped[Any] = mapped_column(
        JSON, nullable=False, comment="配置值（标量或结构化 JSON）",
    )
    config_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="json",
        comment="值类型：float/int/json/str",
    )
    description: Mapped[str] = mapped_column(
        String(500), default="", comment="参数业务说明",
    )
    source: Mapped[str] = mapped_column(
        String(300), default="", comment="参数权威来源（法规/公告/行业头部实践，多源互证）",
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="最后更新人用户ID（审计追溯）",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<RiskConfig({self.config_key}={self.config_value})>"
