"""播种多租户测试数据 + 五类企业案例（幂等）"""
import asyncio
import uuid

from app.database import AsyncSessionLocal
from app.models.tenant import Tenant
from app.models.user import User
from app.models.enterprise import Enterprise, IndustryType, RiskLevelEnhanced
from app.core.security import hash_password
from sqlalchemy import select

# ── 确定性 UUID（基于命名空间 + 名称生成，幂等可复现）──
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _name_uuid(name: str) -> str:
    return str(uuid.uuid5(_NS, name))


async def seed():
    async with AsyncSessionLocal() as db:
        # ── 租户（幂等）──
        tenant_slugs = {
            "org_a": ("t-001", "安永审计一组"),
            "org_b": ("t-002", "安永审计二组"),
        }
        for slug, (tid, name) in tenant_slugs.items():
            existing = await db.execute(select(Tenant).where(Tenant.slug == slug))
            if not existing.scalar_one_or_none():
                db.add(Tenant(id=tid, name=name, slug=slug))
        await db.flush()

        # ── 用户（幂等）──
        users = [
            ("u-001", "admin_t1", "t-001", "admin", "租户A管理员"),
            ("u-002", "viewer_t1", "t-001", "viewer", "租户A查看者"),
            ("u-003", "admin_t2", "t-002", "admin", "租户B管理员"),
        ]
        for uid, uname, tid, role, fullname in users:
            existing = await db.execute(select(User).where(User.username == uname))
            if not existing.scalar_one_or_none():
                db.add(User(
                    id=uid, username=uname,
                    hashed_password=hash_password("a123456"),
                    tenant_id=tid, role=role, full_name=fullname,
                ))
        await db.flush()

        # ── 五类企业案例（幂等）──
        from app.data.mock_data_generator import ENTERPRISE_CONFIGS
        industry_map = {
            "批发零售": IndustryType.WHOLESALE_RETAIL,
            "制造": IndustryType.MANUFACTURING,
            "建筑": IndustryType.CONSTRUCTION,
            "电商": IndustryType.E_COMMERCE,
            "餐饮服务": IndustryType.CATERING,
        }
        risk_map = {
            "low": RiskLevelEnhanced.LOW,
            "medium": RiskLevelEnhanced.MEDIUM,
            "medium_high": RiskLevelEnhanced.MEDIUM_HIGH,
            "high": RiskLevelEnhanced.HIGH,
            "critical": RiskLevelEnhanced.CRITICAL,
        }

        existing_names = set()
        result = await db.execute(select(Enterprise.name))
        for row in result.scalars().all():
            existing_names.add(row)

        for etype, cfg in ENTERPRISE_CONFIGS.items():
            if cfg["name"] in existing_names:
                continue
            db.add(Enterprise(
                id=_name_uuid(f"enterprise-{etype}"),
                name=cfg["name"],
                credit_code=cfg["credit_code"],
                industry=industry_map.get(cfg["industry"], IndustryType.WHOLESALE_RETAIL),
                revenue_annual=cfg["revenue_annual"],
                employee_count=cfg["employee_count"],
                tax_rate_claimed=cfg["tax_rate_industry"],
                cost_rate_claimed=cfg["cost_rate_industry"],
                is_high_tech=cfg["is_high_tech"],
                is_small_micro=cfg["is_small_micro"],
                risk_level=risk_map.get(cfg["risk_level"], RiskLevelEnhanced.LOW),
                tenant_id="t-001",
            ))
            print(f"  + 企业案例: [{etype}] {cfg['name']} ({cfg['industry']} · {cfg['risk_level']})")

        await db.commit()
        print(f"Seeded: tenants + users + enterprises (幂等完成)")


if __name__ == "__main__":
    asyncio.run(seed())
