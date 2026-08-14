#!/usr/bin/env python3
# ruff: noqa: E402  sys.path 引导后的导入为脚本直跑所需（见 _BACKEND_ROOT）
"""幂等生产 schema 同步脚本（migrate_schema.py）

背景：
  生产（Railway）通过 `Base.metadata.create_all` 建表 —— 该 API 只会创建"缺失的表"，
  不会给"已存在的表"补新列，也不会写入种子数据。当新代码引入迁移增量
  （006 企业新列 / 007 轨迹表 / 008 参数表+种子）而生产库仍是旧 schema 时，
  所有查询 enterprises 新列的接口会直接 500：
      ERROR: column enterprises.tax_credit_level does not exist

本脚本对"旧库 / 新库 / 全新库"均幂等：
  1. create_all：创建缺失的新表（risk_score_trajectory / risk_config 等）；
  2. 逐表对比 ORM 模型与现有列，`ADD COLUMN` 补齐缺失列（覆盖 006 及任何未来漂移）；
  3. 补齐 risk_config 唯一索引；
  4. 以 DEFAULT_RISK_CONFIG 为权威基线，仅插入缺失的配置键（不覆盖管理员已调优值）。

用法：在 backend 目录下执行 `python scripts/migrate_schema.py`（start.sh 生产分支自动调用）。
"""
import asyncio
import os
import sys
from decimal import Decimal
from typing import Any

# 允许以 `python scripts/migrate_schema.py` 从 backend 根目录直接运行（start.sh 即此方式）
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.schema import ColumnDefault

import app.models  # noqa: F401  注册全部模型到 Base.metadata
from app.database import Base
from app.core.risk_config import DEFAULT_RISK_CONFIG


def normalize_url(url: str) -> str:
    """与 app/config.py / start.sh 保持一致：postgresql:// → postgresql+asyncpg://"""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _default_sql(arg: Any) -> str:
    """将 Column.server_default.arg 编译为 SQL 片段（支持 text/字符串字面量/func）。"""
    if isinstance(arg, TextClause):
        return f"DEFAULT {arg.text}"
    if isinstance(arg, str):
        return f"DEFAULT '{arg.replace(chr(39), chr(39) * 2)}'"
    return f"DEFAULT {arg}"


def _py_default_sql(arg: Any) -> str | None:
    """将模型 Python 侧 default 编译为 SQL 片段（仅兜底非空列，存量行需要默认值）。"""
    if arg is None:
        return None
    if isinstance(arg, bool):
        return "DEFAULT TRUE" if arg else "DEFAULT FALSE"
    if isinstance(arg, (int, float, Decimal)):
        return f"DEFAULT {arg}"
    if isinstance(arg, str):
        return f"DEFAULT '{arg.replace(chr(39), chr(39) * 2)}'"
    return None


def _sync_missing_columns(sync_conn) -> list[str]:
    """对已存在的表补齐与 ORM 模型不一致的缺失列（幂等，无需 IF NOT EXISTS）。"""
    insp = inspect(sync_conn)
    dialect = sync_conn.dialect
    existing_tables = set(insp.get_table_names())
    added: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # 新表由 create_all 创建，列必然完整
        existing_cols = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            parts = [f'"{col.name}" {col.type.compile(dialect=dialect)}']
            if not col.nullable:
                parts.append("NOT NULL")
            if col.server_default is not None:
                parts.append(_default_sql(col.server_default.arg))
            elif col.default is not None and isinstance(col.default, ColumnDefault):
                # 模型仅声明 Python 侧 default（如 default=False）→ 为存量行补 SQL 默认值，
                # 否则非空表加 NOT NULL 列会失败
                py_default = _py_default_sql(col.default.arg)
                if py_default:
                    parts.append(py_default)
            sync_conn.execute(
                text(f'ALTER TABLE "{table.name}" ADD COLUMN {" ".join(parts)}')
            )
            added.append(f"{table.name}.{col.name}")
    return added


def _ensure_indexes(sync_conn) -> None:
    """补齐唯一索引（存量库由 create_all 创建的 risk_config 可能缺失该索引）。"""
    insp = inspect(sync_conn)
    if "risk_config" in insp.get_table_names():
        sync_conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_risk_config_config_key "
            "ON risk_config (config_key)"
        ))


def _seed_risk_config(sync_conn) -> int:
    """以 DEFAULT_RISK_CONFIG 为权威基线，仅插入缺失键（不覆盖已调优值）。"""
    insp = inspect(sync_conn)
    if "risk_config" not in insp.get_table_names():
        return 0
    from app.models.risk_config import RiskConfig
    table = RiskConfig.__table__
    rows = sync_conn.execute(text("SELECT config_key FROM risk_config")).fetchall()
    existing = {r[0] for r in rows}
    inserted = 0
    for key, meta in DEFAULT_RISK_CONFIG.items():
        if key in existing:
            continue
        sync_conn.execute(table.insert().values(
            config_key=key,
            config_value=meta["value"],
            config_type=meta["type"],
            description=meta["description"],
            source=meta["source"],
        ))
        inserted += 1
    return inserted


async def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: 未设置 DATABASE_URL 环境变量", file=sys.stderr)
        return 1
    engine = create_async_engine(normalize_url(url), pool_pre_ping=True)
    try:
        # 1) 创建缺失的新表（对已存在的表不生效）
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # 2) 补齐缺失列 → 3) 补齐索引 → 4) 幂等种子
        async with engine.begin() as conn:
            def _upgrade(sync_conn) -> None:
                added = _sync_missing_columns(sync_conn)
                _ensure_indexes(sync_conn)
                inserted = _seed_risk_config(sync_conn)
                print(
                    f"schema 同步完成: 补列 {len(added)} 处"
                    f"{('（' + ', '.join(added) + '）') if added else ''}，"
                    f"risk_config 种子新增 {inserted} 键"
                )
            await conn.run_sync(_upgrade)
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
