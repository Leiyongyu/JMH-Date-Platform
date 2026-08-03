from __future__ import annotations

from backend.integrations.lingxing.domains.base import LingXingDomainBase


class LingXingProductsDomain(LingXingDomainBase):
    domain = "products"
    display_name = "商品资料"
    endpoints = {}
