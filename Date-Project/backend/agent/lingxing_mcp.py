"""领星官方 MCP（Streamable HTTP）只读接入：用户在助手里勾选「领星MCP」后，本次运行才提供这些工具。

- 地址 LINGXING_MCP_URL（默认官方 https://openmcp.lingxing.com/mcp-servers/lingxing-mcp），
  鉴权头 X-Mcp-Key 取 LINGXING_MCP_KEY（只放 .env，不入库、不记录）；
- 领星 MCP 有约 300 个工具，其中很多是写操作（改价、删货件、改广告、确认出库……）。这里只开放
  READ_ONLY_TOOLS 白名单里的查询工具，并再按名称里的写操作动词二次拦截；
- 密钥绑定一个领星账号，看到的是该账号权限内的全公司数据，无法按负责人拆分，
  所以只对 AMZ 数据范围为「全部数据」的账号开放；
- 不引入新依赖：用 httpx 实现 initialize → notifications/initialized → tools/list → tools/call，
  响应既可能是 JSON，也可能是 SSE（text/event-stream）。
"""
from __future__ import annotations

import itertools
import json
import logging
import re
import threading
import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from backend.agent.context import SCOPE_AMZ, AgentContext, ToolPermissionError
from backend.agent.tools.base import Tool, ToolArgumentError, ToolResult
from backend.config import settings

LOG = logging.getLogger(__name__)
SOURCE = "lingxing"
TOOL_PREFIX = "lingxing_"
PROTOCOL_VERSION = "2025-03-26"
TOOLS_CACHE_SECONDS = 3600
CALL_TIMEOUT_SEC = 90
MAX_TEXT = 6000
MAX_COLUMNS = 16
SCOPE_NOTE = "领星数据按领星账号权限返回、无法按负责人拆分，只对 AMZ 数据范围为「全部数据」的账号开放"

# 只读白名单（领星帮助文档「领星MCP - 工具能力」中的查询类工具）。服务端没有的会自动跳过。
READ_ONLY_TOOLS: dict[str, str] = {
    "get_my_sids": "店铺列表（sid、店铺名、国家）",
    "get_multi_platform_shop_list": "多平台店铺列表",
    "erp_listing": "Listing 列表",
    "get_fba_stock_list": "FBA 仓库库存",
    "query_fba_valid_list": "FBA 补货建议",
    "query_order_profit_list": "订单利润报表",
    "query_order_profit_list_gross_profit": "订单毛利报表",
    "finance_page_list_msku": "MSKU 维度订单利润",
    "get_profit_report_msku": "MSKU 利润报表",
    "query_product_performance_asin_lists": "ASIN 维度产品表现",
    "analytics_trend_hour_info": "ASIN 360 小时趋势",
    "analytics_order_analysis_lists": "退货分析",
    "analytics_report_reimbursement_list": "亚马逊赔偿报告",
    "analytics_report_adjustment_list": "FBA 调整报告",
    "ad_auth_shops": "广告授权店铺",
    "ad_campaign_report": "广告活动报告",
    "ad_campaign_group_report": "广告组报告",
    "ad_campaign_product_report": "广告商品报告",
    "ad_campaign_keyword_report": "广告关键词报告",
    "ad_campaign_search_term_report": "广告搜索词报告",
    "ad_campaign_targeting_report": "广告投放报告",
    "ad_portfolio_report_shop": "店铺维度广告组合报告",
    "advertising_ad_analyze_keyword": "广告搜索词分析",
    "query_erp_keyword_ranking_asin": "ASIN 维度关键词排名",
    "query_erp_keyword_ranking_keyword": "关键词维度排名",
    "query_erp_competitive_monitor": "竞品监控列表",
    "query_erp_follow_sale_monitor": "ASIN 跟卖监控列表",
    "customer_store_performance_list": "店铺绩效列表",
    "customer_voice_buyer_list": "买家之声",
    "settings_message_inventory_list": "库存预警消息",
}
WRITE_VERBS = re.compile(
    r"(^|_)(create|add|update|modify|edit|delete|del|remove|put|post|cancel|confirm|bind|link|unlink|un_link|"
    r"submit|finish|allocate|release|invalid|archive|revoke|send|set|save|import|upload|apply|approve|"
    r"storage_in|fast_storage)(_|$)", re.IGNORECASE)


class McpError(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.lingxing_mcp_key.strip())


def allowed(context: AgentContext) -> bool:
    return context.access.scope(SCOPE_AMZ) is None


def is_read_only(name: str) -> bool:
    return name in READ_ONLY_TOOLS and not WRITE_VERBS.search(name)


# ---------------------------------------------------------------- 协议客户端

class McpClient:
    """一个进程一个会话；会话失效（404/400 + 会话错误）时自动重新握手一次。线程安全。"""

    def __init__(self, url: str | None = None, key: str | None = None, *, transport: httpx.BaseTransport | None = None):
        self.url = url or settings.lingxing_mcp_url
        self.key = key if key is not None else settings.lingxing_mcp_key.strip()
        self._http = httpx.Client(timeout=httpx.Timeout(CALL_TIMEOUT_SEC, connect=15.0), transport=transport,
                                  follow_redirects=False)
        self._lock = threading.Lock()
        self._session: str | None = None
        self._ready = False
        self._ids = itertools.count(1)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "X-Mcp-Key": self.key, "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        return headers

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        try:
            return self._http.post(self.url, json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise McpError("领星 MCP 响应超时") from exc
        except httpx.HTTPError as exc:
            raise McpError(f"无法连接领星 MCP：{type(exc).__name__}") from exc

    @staticmethod
    def _message(response: httpx.Response, request_id: int) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    try:
                        message = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if message.get("id") == request_id:
                        return message
            raise McpError("领星 MCP 流式响应里没有找到结果")
        try:
            return response.json()
        except ValueError as exc:
            raise McpError("领星 MCP 返回了无法识别的响应") from exc

    def _handshake(self) -> None:
        self._session, self._ready = None, False
        request_id = next(self._ids)
        response = self._post({"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "jmh-data-assistant", "version": "1.0"}}})
        self._check_status(response)
        self._session = response.headers.get("mcp-session-id")
        message = self._message(response, request_id)
        if message.get("error"):
            raise McpError(f"领星 MCP 握手失败：{(message['error'].get('message') or '')[:200]}")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._ready = True

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise McpError("领星 MCP 密钥无效或无权限，请检查 LINGXING_MCP_KEY，并确认已在领星【开放接口】-【MCP】启用")
        if response.status_code == 429:
            raise McpError("领星 MCP 调用过于频繁（每分钟上限 100 次），请稍后再试")
        if response.status_code >= 400:
            raise McpError(f"领星 MCP 返回 HTTP {response.status_code}")

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            for attempt in range(2):
                if not self._ready:
                    self._handshake()
                request_id = next(self._ids)
                response = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
                if response.status_code in (400, 404) and self._session and attempt == 0:
                    self._ready = False  # 会话过期，重新握手后重试一次
                    continue
                self._check_status(response)
                message = self._message(response, request_id)
                if message.get("error"):
                    raise McpError(f"领星 MCP 错误：{(message['error'].get('message') or '')[:300]}")
                return message.get("result") or {}
        raise McpError("领星 MCP 会话重建失败")

    def list_tools(self) -> list[dict[str, Any]]:
        tools, cursor = [], None
        for _ in range(20):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += result.get("tools") or []
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not is_read_only(name):
            raise McpError(f"{name} 不在只读白名单内，已拒绝")
        return self.request("tools/call", {"name": name, "arguments": arguments})


_client_lock = threading.Lock()
_client: McpClient | None = None
_tools_cache: tuple[float, list[Tool]] | None = None


def client() -> McpClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = McpClient()
        return _client


def reset() -> None:
    global _client, _tools_cache
    with _client_lock:
        _client, _tools_cache = None, None


# ---------------------------------------------------------------- 结果转换

def _rows_in(value: Any) -> list[dict] | None:
    """在返回的 JSON 里找最大的「字典列表」作为明细行。"""
    best: list[dict] | None = None
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            if node and all(isinstance(item, dict) for item in node) and (best is None or len(node) > len(best)):
                best = node
            stack.extend(item for item in node if isinstance(item, (dict, list)))
        elif isinstance(node, dict):
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    return best


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def to_tool_result(name: str, result: dict[str, Any]) -> ToolResult:
    texts = [c.get("text") or "" for c in result.get("content") or [] if c.get("type") == "text"]
    text = "\n".join(texts).strip()
    if result.get("isError"):
        raise ValueError(f"领星返回错误：{text[:300] or '未知错误'}")
    data: Any = result.get("structuredContent")
    if data is None and text:
        try:
            data = json.loads(text)
        except ValueError:
            data = None
    title = f"领星：{READ_ONLY_TOOLS.get(name, name)}"
    source = "领星 MCP（实时）"
    if data is None:
        return ToolResult(title=title, summary={"内容": text[:MAX_TEXT]}, source=source,
                          notes=["领星返回的是文本，已原样提供"] if text else ["领星没有返回数据"])
    rows = _rows_in(data) or []
    keys: list[str] = []
    for row in rows[:30]:
        for key, value in row.items():
            if key not in keys and _scalar(value) and len(keys) < MAX_COLUMNS:
                keys.append(key)
    summary = {k: v for k, v in data.items() if _scalar(v)} if isinstance(data, dict) else {}
    clean_rows = [{k: row.get(k) for k in keys} for row in rows]
    notes = [] if rows else ["领星没有返回明细行"]
    if rows and any(not _scalar(v) for row in rows[:30] for v in row.values()):
        notes.append(f"只展示前 {MAX_COLUMNS} 个简单字段，嵌套字段已省略")
    return ToolResult(title=title, summary=summary, columns=[(k, k) for k in keys], rows=clean_rows,
                      source=source, notes=notes)


# ---------------------------------------------------------------- 工具封装

class RemoteArgs(BaseModel):
    """领星工具的参数按其 inputSchema 由模型生成，这里只做 JSON 对象与大小校验，具体校验交给领星。"""
    model_config = ConfigDict(extra="allow")


class LingxingTool(Tool):
    def __init__(self, name: str, description: str, input_schema: dict[str, Any]):
        remote = name

        def handler(context: AgentContext, args: RemoteArgs) -> ToolResult:
            if not allowed(context):
                raise ToolPermissionError(SCOPE_NOTE)
            if SOURCE not in context.sources:
                raise ToolPermissionError("本次提问没有勾选「领星MCP」，只能查询本系统数据")
            try:
                return to_tool_result(remote, client().call(remote, args.model_dump()))
            except McpError as exc:
                raise ValueError(str(exc)) from exc

        super().__init__(TOOL_PREFIX + name, description, RemoteArgs, handler, permission=None,
                         title=f"领星：{READ_ONLY_TOOLS.get(name, name)}", data_scope_all=SCOPE_AMZ,
                         timeout_sec=CALL_TIMEOUT_SEC, requires_source=SOURCE)
        object.__setattr__(self, "input_schema", input_schema)

    def schema(self) -> dict[str, Any]:
        params = {k: v for k, v in (self.input_schema or {}).items() if k not in ("$schema", "title")}
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": params}}

    def parse(self, raw_arguments):
        args = super().parse(raw_arguments)
        if len(json.dumps(args.model_dump(), ensure_ascii=False)) > 4000:
            raise ToolArgumentError("参数过长")
        return args


def tools_for(context: AgentContext) -> list[Tool]:
    """本次运行可用的领星工具：已勾选、已配置密钥、账号有 AMZ 全部数据范围。"""
    global _tools_cache
    if SOURCE not in context.sources or not configured() or not allowed(context):
        return []
    with _client_lock:
        cached = _tools_cache
    if cached and cached[0] > time.monotonic():
        return cached[1]
    remote = client().list_tools()
    tools = []
    for item in remote:
        name = item.get("name") or ""
        if not is_read_only(name):
            continue
        description = f"【领星ERP实时】{READ_ONLY_TOOLS[name]}。{(item.get('description') or '')[:300]}"
        tools.append(LingxingTool(name, description, item.get("inputSchema") or {}))
    with _client_lock:
        _tools_cache = (time.monotonic() + TOOLS_CACHE_SECONDS, tools)
    LOG.info("lingxing mcp tools loaded remote=%s read_only=%s", len(remote), len(tools))
    return tools
