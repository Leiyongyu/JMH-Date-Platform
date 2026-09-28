"""仅用于本机独立调试；正式环境由 backend.main 挂载到 8010。"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.customs_declaration.app import app


if __name__ == "__main__":
    print("报关单生成系统（本机调试）: http://127.0.0.1:5000")
    app.run(debug=False, host="127.0.0.1", port=5000)
