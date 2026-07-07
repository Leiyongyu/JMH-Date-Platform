"""命令行入口：生成月初期初库存货值检查结果。"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.etl.build_monthly_opening_inventory_value import main


if __name__ == "__main__":
    main()
