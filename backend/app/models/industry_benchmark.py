"""
行业基准表 (industry_benchmarks)

宏观内控基准库，存储各行业的标准税负率和成本费用率。
用于企业风险评估时的行业对标（benchmarking）。
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String, Numeric, DateTime, Enum as SAEnum, func, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class AssetType(str, enum.Enum):
    """资产类型"""
    HEAVY = "heavy_asset"       # 重资产（制造、建筑等）
    LIGHT = "light_asset"       # 轻资产（电商、餐饮服务等）


class IndustryBenchmark(Base):
    __tablename__ = "industry_benchmarks"

    # ── 主键 ──
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: _gen_uuid(),
        comment="行业基准ID",
    )

    # ── 行业标识 ──
    industry_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False,
        comment="行业代码（如 C-13 农副食品加工）",
    )
    industry_name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="行业名称（批发零售/制造/建筑/电商/餐饮服务）",
    )

    # ── 资产分类 ──
    asset_type: Mapped[AssetType] = mapped_column(
        SAEnum(AssetType, name="asset_type_enum", create_type=True),
        nullable=False,
        comment="资产类型：heavy_asset 重资产 / light_asset 轻资产",
    )

    # ── 行业基准指标（DECIMAL(10,4) 精度红线） ──
    std_tax_burden_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False,
        comment="行业标准税负率中位数（如 0.0325 表示 3.25%）",
    )
    max_cost_expense_ratio: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False,
        comment="最高成本费用率警戒线阈值（超过此值触发风控预警）",
    )
    depreciation_to_revenue_ratio: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"),
        comment="针对重资产的折旧营收比警戒线（轻资产行业可设为 0）",
    )

    # ── 时间戳 ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(),
    )

    # ── 约束 ──
    __table_args__ = (
        CheckConstraint(
            "std_tax_burden_rate >= 0 AND std_tax_burden_rate <= 1",
            name="ck_benchmark_tax_rate_range",
        ),
        CheckConstraint(
            "max_cost_expense_ratio >= 0 AND max_cost_expense_ratio <= 1",
            name="ck_benchmark_cost_ratio_range",
        ),
    )

    # ── 关联 ──
    enterprises = relationship(
        "Enterprise", back_populates="industry_benchmark",
    )

    def __repr__(self) -> str:
        return (
            f"<IndustryBenchmark({self.industry_code}) "
            f"tax={self.std_tax_burden_rate} "
            f"cost={self.max_cost_expense_ratio}>"
        )


# ── 模块级 UUID 生成 ──
def _gen_uuid() -> str:
    import uuid
    return str(uuid.uuid4())
