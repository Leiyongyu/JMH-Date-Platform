from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


@dataclass(frozen=True)
class Settings:
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "Date-Project")
    template_dir: str = os.getenv(
        "TEMPLATE_DIR",
        r"D:\JMH\出口业务收汇情况表\外汇退税\数据源\模版",
    )
    export_output_dir: str = os.getenv(
        "EXPORT_OUTPUT_DIR", str(PROJECT_ROOT / "exports")
    )
    sku_validation_file: str = os.getenv(
        "SKU_VALIDATION_FILE",
        r"D:\JMH\外汇退税\数据\SKU核对效验.xlsx",
    )
    payer_name: str = os.getenv("PAYER_NAME", "Hong Kong Cammy Yeson Limited")
    lingxing_endpoint: str = os.getenv(
        "LINGXING_ENDPOINT",
        os.getenv("LINGXING_HOST", "https://api.lingxing.com"),
    )
    lingxing_app_id: str = os.getenv("LINGXING_APP_ID", "")
    lingxing_app_secret: str = os.getenv("LINGXING_APP_SECRET", "")
    lingxing_token_refresh_before_sec: int = int(
        os.getenv("LINGXING_TOKEN_REFRESH_BEFORE_SEC", "300")
    )
    lingxing_request_timeout_sec: int = int(
        os.getenv("LINGXING_REQUEST_TIMEOUT_SEC", "30")
    )
    lingxing_max_retries: int = int(os.getenv("LINGXING_MAX_RETRIES", "3"))
    lingxing_page_size: int = int(os.getenv("LINGXING_PAGE_SIZE", "100"))
    lingxing_sign_key: str = os.getenv("LINGXING_SIGN_KEY", "app_id")
    shop_source_database: str = os.getenv("SHOP_SOURCE_DATABASE", "jmh_data_platform")
    python_performance_internal_token: str = os.getenv(
        "PYTHON_PERFORMANCE_INTERNAL_TOKEN", ""
    )


settings = Settings()
