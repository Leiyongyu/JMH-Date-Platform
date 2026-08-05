from __future__ import annotations

from pydantic import BaseModel, Field


class EbayPriceSearchRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1, max_length=50, description="SKU或OE列表")
    site: str = Field("de", pattern="^(de|uk|us)$", description="eBay站点：de/uk/us")
    input_type: str = Field("auto", pattern="^(auto|sku|oe)$", alias="inputType")

    model_config = {"populate_by_name": True}


class EbayPriceExportRequest(BaseModel):
    items: list[dict] = Field(..., min_length=1, description="搜索结果中勾选的商品列表")
