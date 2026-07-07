from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 9000

    erp_db_host: str = "127.0.0.1"
    erp_db_port: int = 3306
    erp_db_user: str
    erp_db_password: str
    erp_db_name: str = "jmh_data_platform"

    report_db_host: str = "127.0.0.1"
    report_db_port: int = 3306
    report_db_user: str
    report_db_password: str
    report_db_name: str = "jmh_report"

    internal_api_secret: str = "change_me"

    # --- lingxing ---
    lingxing_endpoint: str = "http://8.137.177.25/lingxing-proxy"
    lingxing_app_id: str = ""
    lingxing_app_secret: str = ""
    lingxing_connect_timeout: int = 60
    lingxing_read_timeout: int = 120
    lingxing_token_refresh_skew_seconds: int = 300
    lingxing_inventory_wids: str = ""

    # --- scheduler ---
    scheduler_enabled: bool = False
    sync_dim_shop_cron: str = "0 2 * * *"
    sync_dim_warehouse_cron: str = "5 2 * * *"
    lingxing_local_inventory_daily_cron: str = "30 2 * * *"
    monthly_opening_inventory_cron: str = "0 4 2 * *"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
