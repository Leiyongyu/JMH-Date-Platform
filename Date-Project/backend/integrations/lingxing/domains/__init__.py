"""LingXing API domain wrappers."""
from backend.integrations.lingxing.domains.base import (
    LingXingDomainBase,
    LingXingEndpointSpec,
)
from backend.integrations.lingxing.domains.inventory import LingXingInventoryDomain
from backend.integrations.lingxing.domains.order_profit import LingXingOrderProfitDomain
from backend.integrations.lingxing.domains.orders import LingXingOrdersDomain
from backend.integrations.lingxing.domains.products import LingXingProductsDomain
from backend.integrations.lingxing.domains.registry import create_domain, describe_domains

__all__ = [
    "LingXingDomainBase",
    "LingXingEndpointSpec",
    "LingXingInventoryDomain",
    "LingXingOrderProfitDomain",
    "LingXingOrdersDomain",
    "LingXingProductsDomain",
    "create_domain",
    "describe_domains",
]
