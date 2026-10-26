"""示例数据导入：五类单据、附件（PDF/JPG）、审批状态、风险分析报告与人工复核记录。

用法：
    python scripts/seed_demo.py            # 仅当单据表为空时导入
    python scripts/seed_demo.py --reset    # 清空全部数据后重建并导入演示数据
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine
from app.seed import clear_attachments, ensure_base_data, seed_demo
from app.migrations import upgrade_database


def main() -> None:
    parser = argparse.ArgumentParser(description="导入财务单据智能风险审核系统示例数据")
    parser.add_argument("--reset", action="store_true", help="清空全部数据后重新导入")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(bind=engine)
        clear_attachments()
        print("已清空全部数据表与附件文件")
    upgrade_database(engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    started = time.time()
    try:
        ensure_base_data(db)
        created = seed_demo(db)
    finally:
        db.close()

    if created:
        print(f"示例数据导入完成，耗时 {time.time() - started:.1f} 秒")
    else:
        print("单据数据已存在，跳过示例数据导入（使用 --reset 可重新导入）")
    print("演示账号：")
    print("  申请人     zhangwei / User@123（张伟，市场部）")
    print("  申请人     chenchen / User@123（陈晨，研发部）")
    print("  审批人员   lina     / User@123（李娜，财务部）")
    print("  财务人员   wangfang / User@123（王芳，财务部）")
    print("  系统管理员 admin    / Admin@123")


if __name__ == "__main__":
    main()
