"""领星官方 MCP（Streamable HTTP）只读接入：用户在助手里勾选「领星MCP」后，本次运行才提供这些工具。

- 地址 LINGXING_MCP_URL（默认官方 https://openmcp.lingxing.com/mcp-servers/lingxing-mcp），
  鉴权头 X-Mcp-Key 取 LINGXING_MCP_KEY（只放 .env，不入库、不记录）；
- 领星 MCP 有约 300 个工具，其中很多是写操作（改价、删货件、改广告、确认出库……）。这里只开放
  READ_ONLY_TOOLS 白名单里的查询工具，并再按名称里的写操作动词二次拦截；
- 密钥绑定一个领星账号，看到的是该账号权限内的全公司数据，无法按负责人拆分，
  所以只对 AMZ 数据范围为「全部数据」的账号开放；
- 不引入新依赖：用 httpx 实现 initialize → notifications/initialized → tools/call，
  响应既可能是 JSON，也可能是 SSE（text/event-stream）。

领星 MCP 是「网关」形式：MCP 层只有 help / search / action / approval_status 四个工具，
352 个业务工具（265 个 read、87 个 write）都通过 action(toolId, params) 执行。这里的做法：
1. help 分页取业务工具目录，只保留「在白名单内」且「官方 toolType=read」的；
2. search 取每个工具的入参 Schema，按工具逐个提供给模型（函数名 lingxing_<toolId>）；
3. 执行时再校验一次白名单与 toolType，然后调用 action；approval_status 和任何写工具都不提供。
"""
from __future__ import annotations

import itertools
import json
import logging
import re
import threading
import time
from typing import Any, Literal

import httpx
from pydantic import Field, create_model

from backend.agent.context import SCOPE_AMZ, AgentContext, ToolPermissionError
from backend.agent.tools.base import Tool, ToolArgumentError, ToolResult
from backend.config import settings

LOG = logging.getLogger(__name__)
SOURCE = "lingxing"
TOOL_PREFIX = "lingxing_"
PROTOCOL_VERSION = "2025-03-26"
TOOLS_CACHE_SECONDS = 6 * 3600
CALL_TIMEOUT_SEC = 90
MAX_TEXT = 6000
MAX_COLUMNS = 30
KEY_COLUMNS = ("sid", "seller_name", "store_name", "shop_name", "name", "country", "marketplace", "msku",
               "seller_sku", "sku", "local_sku", "asin", "parent_asin", "fnsku", "product_name", "local_name",
               "item_name", "title", "date", "report_date", "data_date", "keyword", "campaign_name",
               # 常用数量、金额字段排在其他字段前面
               "afn_fulfillable_quantity", "available", "available_total", "quantity", "total", "volume",
               "order_items", "sales_amount", "amount", "gross_profit", "gross_margin", "spend", "acos",
               "impressions", "clicks", "orders", "units")
SCOPE_NOTE = "领星数据按领星账号权限返回、无法按负责人拆分，只对 AMZ 数据范围为「全部数据」的账号开放"
# MCP 层允许调用的网关工具；approval_status（审批写操作）不调用
GATEWAY_TOOLS = ("help", "search", "action")

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

    def gateway(self, name: str, arguments: dict[str, Any]) -> Any:
        """调用网关工具（help / search / action），返回业务 JSON；领星判定失败时抛错。"""
        if name not in GATEWAY_TOOLS:
            raise McpError(f"{name} 不是允许调用的领星网关工具")
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(c.get("text") or "" for c in result.get("content") or [] if c.get("type") == "text").strip()
        if result.get("isError"):
            if '"code":102' in text.replace(" ", ""):
                # 领星的「工具参数定义已更新」实际表示参数与 Schema 不符；同时刷新缓存的 Schema
                invalidate_tools()
                raise McpError("领星提示参数不符合该工具的入参定义（code 102）：请只使用参数说明里列出的字段、"
                               "按说明的类型填写（整数不要加引号，JSON 数组字段传字符串）后重试")
            raise McpError(f"领星返回错误：{text[:300] or '未知错误'}")
        try:
            body = json.loads(text)
        except ValueError:
            return {"text": text}
        if isinstance(body, dict) and body.get("success") is False:
            raise McpError(f"领星返回失败：{str(body.get('msg') or body.get('message') or '')[:300]}")
        return body

    def catalog(self) -> dict[str, dict[str, Any]]:
        """help 分页取全部业务工具：{toolId: {displayName, description, toolType}}。"""
        tools, offset = {}, 0
        for _ in range(40):
            body = self.gateway("help", {"limit": 50, "offset": offset})
            data = body.get("data") or {}
            page = data.get("tools") or []
            for item in page:
                tools[item.get("toolId")] = item
            offset += len(page)
            if not page or offset >= int(data.get("total") or 0):
                break
        return tools

    def schema_of(self, tool_id: str) -> dict[str, Any]:
        return (self.gateway("search", {"toolId": tool_id}).get("data") or {})

    def run(self, tool_id: str, params: dict[str, Any], tool_type: str | None) -> Any:
        if not is_read_only(tool_id) or tool_type != "read":
            raise McpError(f"{tool_id} 不在只读白名单内或不是只读工具，已拒绝")
        return self.gateway("action", {"toolId": tool_id, "params": params})


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
    global _client
    with _client_lock:
        _client = None
    invalidate_tools()


def invalidate_tools() -> None:
    """清掉工具目录与参数 Schema 缓存（领星提示参数定义变化时调用）。"""
    global _tools_cache
    with _client_lock:
        _tools_cache = None
    with _schema_lock:
        _schemas.clear()


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


def to_tool_result(name: str, body: Any) -> ToolResult:
    """action 返回的业务 JSON → ToolResult：最大的字典列表作为明细，其余简单字段作为汇总。"""
    title = f"领星：{READ_ONLY_TOOLS.get(name, name)}"
    source = "领星 MCP（实时）"
    if isinstance(body, dict) and set(body) == {"text"}:
        text = body["text"]
        return ToolResult(title=title, summary={"内容": text[:MAX_TEXT]}, source=source,
                          notes=["领星返回的是文本，已原样提供"] if text else ["领星没有返回数据"])
    data = body.get("data", body) if isinstance(body, dict) else body
    rows = _rows_in(data) or []
    scalar_keys: list[str] = []
    for row in rows[:30]:
        for key, value in row.items():
            if key not in scalar_keys and _scalar(value):
                scalar_keys.append(key)
    # 先放店铺、SKU、ASIN、名称这类标识列，再按原顺序补其他字段，避免关键列被挤掉
    keys = [k for k in KEY_COLUMNS if k in scalar_keys]
    keys += [k for k in scalar_keys if k not in keys]
    keys = keys[:MAX_COLUMNS]
    summary = {k: v for k, v in data.items() if _scalar(v) and k not in ("msg", "message", "require_id", "code")} \
        if isinstance(data, dict) else {}
    clean_rows = [{k: row.get(k) for k in keys} for row in rows]
    notes = [] if rows else ["领星没有返回明细行"]
    if rows and any(not _scalar(v) for row in rows[:30] for v in row.values()):
        notes.append(f"只展示前 {MAX_COLUMNS} 个简单字段，嵌套字段已省略")
    return ToolResult(title=title, summary=summary, columns=[(k, k) for k in keys], rows=clean_rows,
                      source=source, notes=notes)


# ---------------------------------------------------------------- 工具封装
#
# 30 个工具的完整入参 Schema 合计约 5.7 万字符，每轮都发给模型会让一次提问消耗 10 万以上 Token。
# 所以只给模型两个小工具：先用 lingxing_tool_params 查看某个工具的参数说明（按需从领星取、缓存），
# 再用 lingxing_query 执行；工具清单以一行一个的形式写在描述里。

PARAMS_TOOL = TOOL_PREFIX + "tool_params"
QUERY_TOOL = TOOL_PREFIX + "query"
_schema_lock = threading.Lock()
_schemas: dict[str, tuple[float, dict[str, Any]]] = {}


def _guard(context: AgentContext) -> None:
    if SOURCE not in context.sources:
        raise ToolPermissionError("本次提问没有勾选「领星MCP」，只能查询本系统数据")
    if not allowed(context):
        raise ToolPermissionError(SCOPE_NOTE)


def tool_schema(tool_id: str) -> dict[str, Any]:
    now = time.monotonic()
    with _schema_lock:
        hit = _schemas.get(tool_id)
        if hit and hit[0] > now:
            return hit[1]
    detail = client().schema_of(tool_id)
    with _schema_lock:
        _schemas[tool_id] = (now + TOOLS_CACHE_SECONDS, detail)
    return detail


def _compact(schema: dict[str, Any]) -> dict[str, Any]:
    """去掉 $schema/title，保留字段、类型、说明、枚举与示例，便于模型照着填。"""
    return {k: v for k, v in (schema or {}).items() if k not in ("$schema", "title")}


def build_tools(catalog: dict[str, dict[str, Any]]) -> list[Tool]:
    offered = {tool_id: entry for tool_id, entry in catalog.items()
               if tool_id in READ_ONLY_TOOLS and entry.get("toolType") == "read" and is_read_only(tool_id)}
    if not offered:
        return []
    ids = tuple(offered)
    listing = "；".join(f"{tool_id}={(entry.get('displayName') or READ_ONLY_TOOLS[tool_id])[:24]}"
                       for tool_id, entry in offered.items())

    params_model = create_model("LingxingParamsArgs", tool_id=(Literal[ids], Field(..., description="领星工具ID")))
    query_model = create_model(
        "LingxingQueryArgs",
        tool_id=(Literal[ids], Field(..., description="领星工具ID")),
        params=(dict[str, Any], Field(default_factory=dict, description="严格按 lingxing_tool_params 返回的参数说明填写")),
    )

    def params_handler(context: AgentContext, args) -> ToolResult:
        _guard(context)
        try:
            detail = tool_schema(args.tool_id)
        except McpError as exc:
            raise ValueError(str(exc)) from exc
        schema = json.dumps(_compact(detail.get("inputSchema") or {}), ensure_ascii=False)
        return ToolResult(title=f"领星工具参数：{offered[args.tool_id].get('displayName') or args.tool_id}",
                          summary={"tool_id": args.tool_id, "说明": (detail.get("description") or "")[:500],
                                   "参数Schema": schema[:MAX_TEXT]},
                          source="领星 MCP", notes=["只能使用 Schema 里列出的字段，类型要一致；分页用 offset/length"])

    def query_handler(context: AgentContext, args) -> ToolResult:
        _guard(context)
        params = args.params or {}
        if len(json.dumps(params, ensure_ascii=False)) > 4000:
            raise ToolArgumentError("参数过长")
        try:
            body = client().run(args.tool_id, params, offered[args.tool_id].get("toolType"))
        except McpError as exc:
            raise ValueError(str(exc)) from exc
        return to_tool_result(args.tool_id, body)

    common = dict(permission=None, data_scope_all=SCOPE_AMZ, timeout_sec=CALL_TIMEOUT_SEC, requires_source=SOURCE)
    return [
        Tool(PARAMS_TOOL, "【领星ERP实时】查看某个领星工具的入参说明。除参数为空的工具外，调用 lingxing_query 前先调用本工具。"
             f"可用工具（只读）：{listing}", params_model, params_handler, title="查看领星工具参数", **common),
        Tool(QUERY_TOOL, "【领星ERP实时】执行一个只读领星工具并返回结果；params 按 lingxing_tool_params 返回的 Schema 填写。",
             query_model, query_handler, title="查询领星", **common),
    ]


def tools_for(context: AgentContext) -> list[Tool]:
    """本次运行可用的领星工具：已勾选、已配置密钥、账号有 AMZ 全部数据范围。"""
    global _tools_cache
    if SOURCE not in context.sources or not configured() or not allowed(context):
        return []
    with _client_lock:
        cached = _tools_cache
    if cached and cached[0] > time.monotonic():
        return cached[1]
    started = time.monotonic()
    catalog = client().catalog()
    tools = build_tools(catalog)
    with _client_lock:
        _tools_cache = (time.monotonic() + TOOLS_CACHE_SECONDS, tools)
    LOG.info("lingxing mcp catalog loaded tools=%s seconds=%.1f", len(catalog), time.monotonic() - started)
    return tools
