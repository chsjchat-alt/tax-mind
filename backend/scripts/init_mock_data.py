"""
一键初始化模拟数据脚本

将三类企业（A=正常、B=轻度风险、C=重度风险）的模拟数据导入数据库。

使用方法：
    # 导入全部三类企业
    cd backend
    python scripts/init_mock_data.py

    # 仅导入指定企业
    python scripts/init_mock_data.py --enterprise A
    python scripts/init_mock_data.py --enterprise B,C

依赖：
    1. PostgreSQL 数据库运行中（见 docker-compose.yml）
    2. 已执行 alembic upgrade head

注意：
    本脚本覆盖数据库中原有的模拟数据，请谨慎执行。
    生产环境请勿执行本脚本。
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 添加 backend 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


async def _init_db():
    """初始化数据库连接"""
    from app.database import init_db
    await init_db()
    from app.database import AsyncSessionLocal
    return AsyncSessionLocal


async def import_enterprises(enterprise_types: list[str], dry_run: bool = False, force: bool = False):
    """
    导入指定类型企业的模拟数据。

    Args:
        enterprise_types: 企业类型列表 ['A', 'B', 'C']
        dry_run: 仅生成数据不写入数据库
        force: 强制重新导入（删除已有同名企业数据后重建）
    """
    from app.data.mock_data_generator import generate_mock_data

    print("=" * 60)
    print("  税智·心判 — 模拟数据初始化")
    print("=" * 60)
    print()
    print("【重要声明】")
    print("根据德勤比赛规则——")
    print("'禁止使用任何真实企业或个人的保密信息'、")
    print("'作品中所有所涉数据须为自行构造的模拟数据，")
    print("或经脱敏处理至无法识别特定主体的数据'——")
    print("本脚本生成的所有数据均为自行构造的模拟数据，")
    print("不涉及任何真实企业或个人的保密信息。")
    print()

    for et in enterprise_types:
        print(f"\n{'─' * 40}")
        print(f"  企业类型: {et}")
        print(f"{'─' * 40}")

        data = generate_mock_data(et)
        info = data["enterprise_info"]
        meta = data["_meta"]

        print(f"  企业名称: {info['name']}")
        print(f"  行业: {info['industry']}")
        print(f"  年营收: {info['revenue_annual']/10000:.0f}万元")
        print(f"  风险等级: {info['risk_level']}")
        print(f"  银行流水: {meta['bank_transactions_count']} 条")
        print(f"  发票数据: {meta['invoices_count']} 张")
        print(f"  纳税申报: {meta['tax_declarations_count']} 条")
        print(f"  合同台账: {meta['contracts_count']} 份")
        print(f"  财务报表: {meta['financial_statements_count']} 份")

        if dry_run:
            print(f"  [DRY RUN] 跳过数据库写入")
            continue

        # 写入数据库
        try:
            async_session_factory = await _init_db()
            async with async_session_factory() as session:
                from sqlalchemy import select
                from app.models.enterprise import Enterprise

                # 幂等性：检查是否已存在同名企业
                existing = await session.execute(
                    select(Enterprise).where(Enterprise.name == info["name"])
                )
                existing_enterprise = existing.scalar_one_or_none()

                if existing_enterprise:
                    if force:
                        await session.delete(existing_enterprise)
                        await session.flush()
                        print(f"  [FORCE] 已删除已有数据，重新导入...")
                    else:
                        print(f"  ⚠ 企业 '{info['name']}' 已存在 (id: {existing_enterprise.id})，跳过导入。")
                        print(f"  提示: 使用 --force 参数可强制重新导入")
                        continue

                from app.data.mock_data_generator import load_mock_data_to_db
                enterprise_id = await load_mock_data_to_db(et, session)
                await session.commit()
                print(f"  [OK] 已导入数据库 (enterprise_id: {enterprise_id})")
        except Exception as e:
            print(f"  [FAIL] 数据库写入失败: {e}")
            if "connect" in str(e).lower() or "connection" in str(e).lower():
                print("  提示: 请确保 PostgreSQL 数据库已启动")
                print("  运行: docker-compose up -d postgres")

    print(f"\n{'=' * 60}")
    print(f"  初始化完成: {len(enterprise_types)} 家企业")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description="税智·心判 模拟数据初始化脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/init_mock_data.py                     # 导入全部三类企业
  python scripts/init_mock_data.py --enterprise A      # 仅导入企业A
  python scripts/init_mock_data.py --enterprise B,C    # 导入企业B和C
  python scripts/init_mock_data.py --dry-run           # 仅生成数据不入库
        """,
    )
    parser.add_argument(
        "--enterprise",
        type=str,
        default="A,B,C",
        help="企业类型，用逗号分隔 (默认: A,B,C)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅生成数据，不写入数据库",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新导入（删除已有同名企业数据后重建）",
    )
    args = parser.parse_args()

    enterprise_types = [t.strip() for t in args.enterprise.split(",")]
    valid_types = {"A", "B", "C"}
    invalid = [t for t in enterprise_types if t not in valid_types]
    if invalid:
        print(f"错误: 无效的企业类型 {invalid}, 有效值: A, B, C")
        sys.exit(1)

    asyncio.run(import_enterprises(enterprise_types, dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
