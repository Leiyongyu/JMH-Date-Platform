from __future__ import annotations

from datetime import date
from typing import Any

from backend.integrations.lingxing.domains.base import LingXingDomainBase


class LingXingAfterSalesDomain(LingXingDomainBase):
    domain = "after_sales"
    display_name = "Amazon售后订单"

    def fetch(
        self,
        sids: list[str],
        start_date: date,
        end_date_exclusive: date,
        date_type: int = 1,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        return self.paginated_request(
            "erp/sc/routing/amzod/order/afterSaleList",
            {
                "sid": ",".join(sids),
                "start_date": start_date.isoformat(),
                "end_date": end_date_exclusive.isoformat(),
                "date_type": date_type,
                "after_type": "1,2,3",
            },
            page_size=page_size,
            max_pages=500,
        )
