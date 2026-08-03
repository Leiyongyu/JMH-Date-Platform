from __future__ import annotations

from datetime import date
from typing import Any

from backend.integrations.lingxing.domains.base import LingXingDomainBase


class LingXingOrderProfitDomain(LingXingDomainBase):
    domain = "order_profit"
    display_name = "Amazon订单利润"

    def fetch_monthly_profit(
        self,
        sids: list[str],
        start_date: date,
        end_date: date,
        currency_code: str = "CNY",
        page_size: int = 5000,
    ) -> list[dict[str, Any]]:
        return self.paginated_request(
            "basicOpen/finance/mreport/OrderProfit",
            {
                "sids": sids,
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "currencyCode": currency_code,
            },
            page_size=page_size,
            max_pages=200,
        )
