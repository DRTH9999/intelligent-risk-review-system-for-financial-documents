"""数据库初始化：创建全部数据表并写入基础数据（角色、用户、流程、规则、供应商、市场价）。

用法：
    python scripts/init_db.py            # 保留已有数据，仅补齐表结构与基础数据
    python scripts/init_db.py --reset    # 删除全部表后重建（会清空数据）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine
from app.seed import clear_attachments, ensure_base_data
from app.migrations import upgrade_database


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化财务单据智能风险审核系统数据库")
    parser.add_argument("--reset", action="store_true", help="删除全部数据表后重建")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(bind=engine)
        clear_attachments()
        print("已删除全部数据表与附件文件")
    upgrade_database(engine)
    Base.metadata.create_all(bind=engine)
    print("数据表创建完成")

    db = SessionLocal()
    try:
        ensure_base_data(db)
    finally:
        db.close()
    print("基础数据初始化完成")
    print("默认账号：admin / Admin@123　zhangwei / User@123　lina / User@123　wangfang / User@123")


if __name__ == "__main__":
    main()
