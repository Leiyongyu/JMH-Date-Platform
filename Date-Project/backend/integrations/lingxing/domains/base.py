from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.config import settings
from backend.integrations.lingxing.client import LingXingClient


@dataclass(frozen=True)
class LingXingEndpointSpec:
    key: str
    name: str
    path: str
    paginated: bool = True
    description: str = ""


class LingXingDomainBase:
    domain = "base"
    display_name = "领星通用接口"
    endpoints: dict[str, LingXingEndpointSpec] = {}

    def __init__(self, client: LingXingClient | None = None) -> None:
        self.client = client or LingXingClient()

    def describe(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "display_name": self.display_name,
            "endpoints": [
                {
                    "key": endpoint.key,
                    "name": endpoint.name,
                    "path": endpoint.path,
                    "paginated": endpoint.paginated,
                    "description": endpoint.description,
                }
                for endpoint in self.endpoints.values()
            ],
            "custom_path_supported": True,
        }

    def endpoint(self, key: str) -> LingXingEndpointSpec:
        try:
            return self.endpoints[key]
        except KeyError as exc:
            raise ValueError(f"领星 {self.display_name} 不存在端点 key={key}") from exc

    def request(self, path: str, body: dict[str, Any] | None = None) -> dict:
        return self.client.post_signed_query_auth(path, body or {})

    def request_endpoint(
        self,
        endpoint_key: str,
        body: dict[str, Any] | None = None,
    ) -> dict:
        endpoint = self.endpoint(endpoint_key)
        return self.request(endpoint.path, body)

    def paginated_request(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        page_size: int | None = None,
        max_pages: int = 100,
        offset_key: str = "offset",
        length_key: str = "length",
    ) -> list[dict]:
        page_size = page_size or settings.lingxing_page_size
        rows: list[dict] = []
        expected_total = 0
        base_body = dict(body or {})
        for page in range(max_pages):
            offset = page * page_size
            payload = {**base_body, offset_key: offset, length_key: page_size}
            response = self.request(path, payload)
            code = response.get("code")
            if code is not None and str(code).lower() not in {"0", "200", "ok", "success"}:
                message = response.get("message") or response.get("msg") or "未知错误"
                raise RuntimeError(f"领星接口返回失败：code={code}，message={message}")
            batch, total = extract_rows_and_total(response)
            expected_total = total
            rows.extend(batch)
            if len(rows) >= total:
                break
            if not batch:
                raise RuntimeError(
                    f"领星分页数据不完整：应返回{total}条，"
                    f"实际仅取得{len(rows)}条"
                )
        if len(rows) < expected_total:
            raise RuntimeError(
                f"领星分页超过最大页数{max_pages}：应返回"
                f"{expected_total}条，实际仅取得{len(rows)}条"
            )
        return rows

    def paginated_endpoint(
        self,
        endpoint_key: str,
        body: dict[str, Any] | None = None,
        page_size: int | None = None,
        max_pages: int = 100,
    ) -> list[dict]:
        endpoint = self.endpoint(endpoint_key)
        return self.paginated_request(
            endpoint.path,
            body,
            page_size=page_size,
            max_pages=max_pages,
        )


def extract_rows_and_total(response: dict) -> tuple[list[dict], int]:
    data = response.get("data")
    if isinstance(data, list):
        return data, int(response.get("total") or len(data))
    if isinstance(data, dict):
        rows = data.get("list") or data.get("data") or data.get("rows") or []
        total = data.get("total") or response.get("total") or len(rows)
        return rows if isinstance(rows, list) else [], int(total or 0)
    return [], 0
