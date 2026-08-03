from __future__ import annotations

from backend.integrations.lingxing.domains.base import LingXingDomainBase


class LingXingOrdersDomain(LingXingDomainBase):
    domain = "orders"
    display_name = "订单"
    endpoints = {}
