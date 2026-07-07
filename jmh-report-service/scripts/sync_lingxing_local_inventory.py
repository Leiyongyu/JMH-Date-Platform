"""命令行入口：同步领星本地仓库存报表到 STG/ODS。

示例：
  python scripts/sync_lingxing_local_inventory.py --full
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.etl.sync_lingxing_local_inventory import main


if __name__ == "__main__":
    main()
