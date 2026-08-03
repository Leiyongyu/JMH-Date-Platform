from __future__ import annotations

from backend.integrations.lingxing.domains.base import LingXingDomainBase


class LingXingInventoryDomain(LingXingDomainBase):
    domain = "inventory"
    display_name = "库存"
    endpoints = {}
