import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── 领星 API ──
    lingxing_api_base: str = os.getenv("LINGXING_ENDPOINT", "https://openapi.lingxing.com")
    lingxing_api_token: str = ""
    lingxing_use_mock: bool = False
    lingxing_sku_query_path: str = "/openapi/listing/list"
    lingxing_sku_param_name: str = "sku"
    lingxing_request_method: str = "GET"
    lingxing_auth_mode: str = "oauth"
    lingxing_app_key: str = os.getenv("LINGXING_APP_ID", "")
    lingxing_app_secret: str = os.getenv("LINGXING_APP_SECRET", "")
    lingxing_relation_tag_path: str = "/basicOpen/listingManage/queryListingRelationTagList"
    lingxing_relation_id_field: str = "relation_id"
    lingxing_sid_field: str = "sid"
    lingxing_default_sid: int = 0
    lingxing_sellers_path: str = "/erp/sc/data/seller/lists"
    lingxing_us_country_codes: str = "US,美国"
    lingxing_us_sids: str = ""
    lingxing_vc_listing_page_path: str = "/basicOpen/listingManage/vcListing/pageList"
    lingxing_vc_default_store_ids: str = ""
    lingxing_vc_fallback_page_length: int = 200
    lingxing_vc_fallback_max_pages: int = 5
    lingxing_amazon_listing_path: str = "/erp/sc/data/mws/listing"
    lingxing_amazon_listing_default_length: int = 100
    lingxing_amazon_product_search_path: str = "/listing/publish/openapi/amazon/product/search"
    lingxing_publish_store_id: int = 0

    # Synology NAS (图片来源)
    nas_enabled: bool = True
    nas_url: str = "https://jmh001.cn3.quickconnect.cn"
    nas_username: str = ""
    nas_password: str = ""
    nas_base_path: str = "/JMH/供应链中心"
    nas_cache_dir: str = str(Path(__file__).resolve().parents[2] / "outputs" / "image_sop" / "nas_cache")
    nas_timeout: int = 30
    nas_download_max_concurrent: int = 3
    nas_search_max_workers: int = 3
    nas_search_top_dir_cache_ttl: int = 600
    nas_image_collect_max_depth: int = 2
    nas_thumb_preload_max: int = 120
    nas_thumb_preload_workers: int = 4

    openai_api_base: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    deepseek_api_base: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/v1"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    ai_provider: str = "deepseek"
    ai_standard_max_concurrent: int = 2
    ai_premium_max_concurrent: int = 1
    ai_total_max_concurrent: int = 2
    ai_request_retries: int = 2
    ai_request_timeout: int = 180
    ai_profile_cache_ttl_hours: int = 72
    sop_generation_max_concurrent: int = 1
    sop_image_count: int = 7
    sop_image_size: str = "1600*1600"
    sop_premium_image_count: int = 6
    sop_premium_image_size: str = "高级A+尺寸"

    db_path: str = "mysql"
    export_dir: str = os.getenv("IMAGE_SOP_EXPORT_DIR", str(Path(__file__).resolve().parents[2] / "outputs" / "image_sop" / "exports"))
    upload_dir: str = os.getenv("IMAGE_SOP_UPLOAD_DIR", str(Path(__file__).resolve().parents[2] / "outputs" / "image_sop" / "uploads"))
    upload_max_file_mb: int = 12
    upload_max_total_mb: int = 40
    web_ref_dir: str = os.getenv("IMAGE_SOP_WEB_REF_DIR", str(Path(__file__).resolve().parents[2] / "outputs" / "image_sop" / "web_refs"))
    web_search_enabled: bool = False
    web_search_engine: str = "baidu"
    web_search_timeout: int = 15         # 下载图片超时(秒)，服务端网络通常较慢
    web_search_max_concurrent: int = 3   # 并发搜索/下载数
    web_search_max_image_size_mb: int = 5
    web_search_proxy: str = ""

    ebay_client_id: str = ""
    ebay_client_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def active_ai_provider(self) -> str:
        """尊重 ai_provider 配置；无法匹配时回退到有 key 的 provider。"""
        provider = self.ai_provider.strip().lower()
        if provider == "deepseek" and self.deepseek_api_key:
            return "deepseek"
        if provider == "openai" and self.openai_api_key:
            return "openai"
        # 回退：哪个有 key 用哪个
        if self.deepseek_api_key:
            return "deepseek"
        if self.openai_api_key:
            return "openai"
        return "fallback"

    @property
    def active_ai_api_base(self) -> str:
        if self.active_ai_provider == "openai":
            return self.openai_api_base.rstrip("/")
        return self.deepseek_api_base.rstrip("/")

    @property
    def active_ai_api_key(self) -> str:
        if self.active_ai_provider == "openai":
            return self.openai_api_key
        return self.deepseek_api_key

    @property
    def active_ai_model(self) -> str:
        if self.active_ai_provider == "openai":
            return self.openai_model
        return self.deepseek_model

    @property
    def export_path(self) -> Path:
        return Path(self.export_dir)

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def db_file_path(self) -> Path:
        return Path(self.db_path)

    @property
    def web_ref_path(self) -> Path:
        return Path(self.web_ref_dir)

    @property
    def nas_cache_path(self) -> Path:
        return Path(self.nas_cache_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
