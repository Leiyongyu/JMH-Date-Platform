from __future__ import annotations

from pydantic import BaseModel, Field


class ListingData(BaseModel):
    sku: str
    asin: str = ""
    asin_url: str = ""
    title: str
    bullet_points: list[str]
    description: str
    keywords: list[str]
    oe_numbers: list[str] = Field(default_factory=list)
    listing_tags: list[str] = Field(default_factory=list)
    scrape_status: str = "not_attempted"
    scrape_reason: str = ""
    scrape_action: str = ""
    data_source: str = ""
    source_updated_at: str = ""


class EbayParseUrlRequest(BaseModel):
    url: str
    site: str | None = None


class ProductAnalysis(BaseModel):
    function: str = ""
    installation: str = ""
    inspection: str = ""
    maintenance: str = ""
    compatibility: str = ""
    oe_numbers: str = ""
    quality: str = ""


class CopyBlock(BaseModel):
    headline: str
    subheadline: str
    body: str
    keywords: list[str] = Field(default_factory=list)


class ImageRequirement(BaseModel):
    index: int
    theme: str = ""
    size: str
    copy_text: str
    design_request: str
    reference_image: str
    reference_images: list[str] = Field(default_factory=list)
    detail_image: str = ""         # 细节图 URL（运营上传的产品特写）
    scene_image: str = ""          # 场景物品图 URL（AI搜索/运营上传的使用场景）
    main_image: str = ""
    reference_source: str = ""     # "main"|"main_scene"|"detail"|"scene"|"composite"
    reference_search_query: str = ""
    reference_search_used: bool = False


class SopResult(BaseModel):
    sku: str
    draft_id: str = ""
    listing_data: ListingData
    product_analysis: ProductAnalysis = Field(default_factory=ProductAnalysis)
    copy_block: CopyBlock
    image_requirements: list[ImageRequirement]
    excel_file: str = ""
    scrape_feedback: dict[str, str] = Field(default_factory=dict)
    ai_provider: str = ""


class SopExportRequest(BaseModel):
    draft_id: str
