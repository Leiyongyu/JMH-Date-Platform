from __future__ import annotations

from typing import Any

from backend.integrations.lingxing.domains.base import (
    LingXingDomainBase,
    LingXingEndpointSpec,
)


class LingXingCurrencyDomain(LingXingDomainBase):
    domain = "currency"
    display_name = "领星月度汇率"
    endpoints = {
        "monthly_rates": LingXingEndpointSpec(
            key="monthly_rates",
            name="查询汇率",
            path="erp/sc/routing/finance/currency/currencyMonth",
            paginated=False,
            description="按月份读取领星汇率管理数据",
        )
    }

    def fetch_monthly_rates(self, rate_month: str) -> list[dict[str, Any]]:
        response = self.request(
            self.endpoint("monthly_rates").path,
            {"date": rate_month},
        )
        code = response.get("code")
        if code is not None and str(code).lower() not in {
            "0", "200", "ok", "success"
        }:
            message = response.get("message") or response.get("msg") or "未知错误"
            raise RuntimeError(
                f"领星汇率接口返回失败：code={code}，message={message}，"
                f"error_details={response.get('error_details')}"
            )
        rows = response.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("领星汇率接口返回的data不是数组")
        return [row for row in rows if isinstance(row, dict)]
