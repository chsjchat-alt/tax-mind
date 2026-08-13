"""查询审计日志"""
import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text


async def query():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT id, user_id, username, tenant_id, method, path, "
            "status_code, business_code, duration_ms, created_at "
            "FROM audit_logs ORDER BY created_at DESC LIMIT 20"
        ))
        rows = list(r)
        if not rows:
            print("No audit logs found!")
            return

        for row in r.mappings():
            ts = row["created_at"].strftime("%H:%M:%S") if row["created_at"] else "-"
            print(
                f"{ts} {row['method']:6} {row['status_code']:3} "
                f"{row['business_code'] or '-':>5} {row['duration_ms']:4}ms "
                f"{(row['username'] or 'anon'):>12} t={(row['tenant_id'] or '-')[:6]:6} "
                f"{str(row['path'])[:60]}"
            )
        print(f"\nTotal: {len(list(r.mappings()))} logs")


asyncio.run(query())
