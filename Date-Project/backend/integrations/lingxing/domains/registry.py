from __future__ import annotations

from backend.integrations.lingxing.client import LingXingClient
from backend.integrations.lingxing.domains.base import LingXingDomainBase
from backend.integrations.lingxing.domains.currency import LingXingCurrencyDomain
from backend.integrations.lingxing.domains.inventory import LingXingInventoryDomain
from backend.integrations.lingxing.domains.order_profit import LingXingOrderProfitDomain
from backend.integrations.lingxing.domains.orders import LingXingOrdersDomain
from backend.integrations.lingxing.domains.products import LingXingProductsDomain


DOMAIN_CLASSES: dict[str, type[LingXingDomainBase]] = {
    "base": LingXingDomainBase,
    "currency": LingXingCurrencyDomain,
    "products": LingXingProductsDomain,
    "inventory": LingXingInventoryDomain,
    "orders": LingXingOrdersDomain,
    "order_profit": LingXingOrderProfitDomain,
}


def create_domain(
    domain: str,
    client: LingXingClient | None = None,
) -> LingXingDomainBase:
    try:
        domain_class = DOMAIN_CLASSES[domain]
    except KeyError as exc:
        supported = "、".join(sorted(DOMAIN_CLASSES))
        raise ValueError(f"不支持的领星业务域: {domain}，可选: {supported}") from exc
    return domain_class(client=client)


def describe_domains() -> list[dict]:
    return [domain_class().describe() for domain_class in DOMAIN_CLASSES.values()]
