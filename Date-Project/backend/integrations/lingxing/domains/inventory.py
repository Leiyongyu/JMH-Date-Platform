from __future__ import annotations

from backend.integrations.lingxing.domains.base import (
    LingXingDomainBase,
    LingXingEndpointSpec,
)


class LingXingInventoryDomain(LingXingDomainBase):
    domain = "inventory"
    display_name = "库存"
    endpoints = {
        "fba_monthly_detail": LingXingEndpointSpec(
            key="fba_monthly_detail",
            name="库存报表-FBA-新版-明细",
            path="cost/center/openApi/fba/detail/query",
            description="按月份和Amazon seller_id查询FBA库存报表明细",
        ),
        "overseas_monthly_detail": LingXingEndpointSpec(
            key="overseas_monthly_detail",
            name="库存报表-海外仓-新报表-明细",
            path="inventory/center/openapi/storageReport/overseas/detail/page",
            description="按日期和系统仓库ID查询海外仓库存报表明细",
        ),
        "local_monthly_detail": LingXingEndpointSpec(
            key="local_monthly_detail",
            name="库存报表-本地仓-新报表-明细",
            path="inventory/center/openapi/storageReport/local/detail/page",
            description="按日期和系统仓库ID查询本地仓库存报表明细",
        ),
    }
