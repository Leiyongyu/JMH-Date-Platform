"""领星 MCP（网关形式 help / search / action）：握手与 SSE、白名单 + 官方 read 标记、勾选才提供、数据范围、结果转换。"""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from backend.agent import lingxing_mcp as lx
from backend.agent import runner as runner_module
from backend.agent.context import SCOPE_AMZ, AgentAccess, AgentContext
from tests.test_ai_agent import FakeConversations, FakeRepo, ScriptedLlm, call, reply

CATALOG = [
    {"toolId": "get_my_sids", "displayName": "查询我的店铺列表", "toolType": "read"},
    {"toolId": "get_fba_stock_list", "displayName": "查询 FBA 仓库库存", "toolType": "read"},
    # 白名单里有、但领星标为 write：不提供
    {"toolId": "erp_listing", "displayName": "查询 Listing 列表", "toolType": "write"},
    {"toolId": "put_campaigns_sp", "displayName": "修改 SP 广告活动", "toolType": "write"},
]
SCHEMAS = {
    "get_my_sids": {"type": "object", "properties": {}},
    "get_fba_stock_list": {"$schema": "x", "type": "object", "additionalProperties": False,
                           "properties": {"offset": {"type": "integer"}, "search_value": {"type": "string"}}},
}


def text_result(request_id, payload, *, error=False):
    return {"jsonrpc": "2.0", "id": request_id, "result": {
        "content": [{"type": "text", "text": payload if isinstance(payload, str) else json.dumps(payload)}],
        "isError": error}}


class FakeServer:
    def __init__(self):
        self.actions: list[dict] = []
        self.keys: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.keys.add(request.headers.get("x-mcp-key", ""))
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}},
                                  headers={"mcp-session-id": "s1"})
        if method == "notifications/initialized":
            return httpx.Response(202)
        assert request.headers.get("mcp-session-id") == "s1"
        name, args = body["params"]["name"], body["params"]["arguments"]
        if name == "help":
            # help 用 SSE 返回，分两页
            page = CATALOG[args["offset"]:args["offset"] + 2]
            payload = {"code": 1, "success": True, "data": {"total": len(CATALOG), "tools": page}}
            event = json.dumps(text_result(body["id"], payload))
            return httpx.Response(200, text=f"event: message\ndata: {event}\n\n",
                                  headers={"content-type": "text/event-stream"})
        if name == "search":
            return httpx.Response(200, json=text_result(body["id"], {"code": 1, "success": True, "data": {
                "toolId": args["toolId"], "description": "说明", "inputSchema": SCHEMAS[args["toolId"]]}}))
        assert name == "action"
        self.actions.append(args)
        if "length" in args["params"]:
            return httpx.Response(200, json=text_result(
                body["id"], 'call failed, status: 422, response: {"code":102,"msg":"工具参数定义已更新"}', error=True))
        data = {"total": 2, "msg": "ok", "list": [
            {"available": 120, "sku": "A-1", "nested": {"x": 1}}, {"available": 30, "sku": "B-2", "nested": {}}]}
        return httpx.Response(200, json=text_result(body["id"], {"code": 1, "success": True, "data": data}))


@pytest.fixture
def server(monkeypatch):
    fake = FakeServer()
    monkeypatch.setattr(lx, "settings", replace(lx.settings, lingxing_mcp_key="k-123",
                                                lingxing_mcp_url="https://mcp.test/lingxing"))
    lx.reset()
    monkeypatch.setattr(lx, "_client", lx.McpClient(transport=httpx.MockTransport(fake)))
    yield fake
    lx.reset()


def ctx(sources=("lingxing",), amz="all"):
    scopes = {SCOPE_AMZ: None if amz == "all" else ["张三"]}
    return AgentContext(1, "tester", AgentAccess(frozenset({"finance:salesDashboard:list"}), scopes), "req",
                        sources=frozenset(sources))


def by_name(tools):
    return {t.name: t for t in tools}


def test_only_allowlisted_tools_marked_read_are_offered(server):
    tools = by_name(lx.tools_for(ctx()))
    assert set(tools) == {"lingxing_tool_params", "lingxing_query"}
    enum = tools["lingxing_query"].schema()["function"]["parameters"]["properties"]["tool_id"]["enum"]
    assert enum == ["get_my_sids", "get_fba_stock_list"]  # erp_listing 被领星标为 write，不提供
    assert "get_fba_stock_list=查询 FBA 仓库库存" in tools["lingxing_tool_params"].description
    params = tools["lingxing_tool_params"]
    schema = params.handler(ctx(), params.parse({"tool_id": "get_fba_stock_list"})).summary["参数Schema"]
    assert '"offset"' in schema and "$schema" not in schema
    with pytest.raises(lx.ToolArgumentError):
        tools["lingxing_query"].parse({"tool_id": "put_campaigns_sp", "params": {}})
    assert server.keys == {"k-123"}
    with pytest.raises(lx.McpError, match="已拒绝"):
        lx.client().run("put_campaigns_sp", {}, "write")
    with pytest.raises(lx.McpError, match="已拒绝"):
        lx.client().run("erp_listing", {}, "write")  # 白名单内但领星标为 write
    with pytest.raises(lx.McpError, match="网关工具"):
        lx.client().gateway("approval_status", {"approval_ref": "x"})


def test_action_result_puts_identifier_columns_first_and_skips_nested(server):
    tool = by_name(lx.tools_for(ctx()))["lingxing_query"]
    result = tool.handler(ctx(), tool.parse({"tool_id": "get_fba_stock_list", "params": {"offset": 0}}))
    assert [c[0] for c in result.columns] == ["sku", "available"]
    assert result.rows[0] == {"sku": "A-1", "available": 120}
    assert result.summary == {"total": 2}
    assert server.actions[-1] == {"toolId": "get_fba_stock_list", "params": {"offset": 0}}


def test_code_102_becomes_actionable_hint_and_refreshes_schema(server):
    tool = by_name(lx.tools_for(ctx()))["lingxing_query"]
    with pytest.raises(ValueError, match="入参定义"):
        tool.handler(ctx(), tool.parse({"tool_id": "get_fba_stock_list", "params": {"length": 5}}))
    assert lx._tools_cache is None and not lx._schemas


def test_not_checked_or_limited_scope_or_unconfigured_returns_no_tools(server, monkeypatch):
    assert lx.tools_for(ctx(sources=())) == []
    assert lx.tools_for(ctx(amz="self")) == []
    assert server.actions == []
    monkeypatch.setattr(lx, "settings", replace(lx.settings, lingxing_mcp_key=""))
    assert lx.tools_for(ctx()) == []


def test_text_body_is_kept_as_text():
    text = lx.to_tool_result("get_my_sids", {"text": "共3个店铺"})
    assert text.summary["内容"] == "共3个店铺" and not text.rows


def test_status_codes_map_to_readable_errors():
    client = lx.McpClient("https://mcp.test", "bad", transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(lx.McpError, match="LINGXING_MCP_KEY"):
        client.catalog()


def run_agent(context, external, llm):
    repo = FakeRepo()
    agent = runner_module.AgentRunner(llm=llm, tools=[], repo=repo, conversations=FakeConversations(),
                                      external_tools=external)
    asyncio.run(agent.run("run-1", context, "conv-1", "领星FBA库存多少", None))
    return repo


def test_runner_offers_lingxing_tools_only_when_checked(server):
    llm = ScriptedLlm([reply(tool_calls=[call("a", "lingxing_query", tool_id="get_fba_stock_list",
                                              params={"offset": 0})]),
                       reply(content="A-1 有 120 件")])
    repo = run_agent(ctx(), lx.tools_for, llm)
    offered = {s["function"]["name"] for s in llm.requests[0]["tools"]}
    assert {"lingxing_query", "lingxing_tool_params"} <= offered
    assert "勾选了「领星MCP」" in llm.requests[0]["messages"][0]["content"]
    assert repo.steps[0]["status"] == "completed"

    unchecked = ScriptedLlm([reply(tool_calls=[call("a", "lingxing_query", tool_id="get_my_sids")]),
                             reply(content="请勾选")])
    repo = run_agent(ctx(sources=()), lx.tools_for, unchecked)
    assert not any(s["function"]["name"].startswith("lingxing_") for s in unchecked.requests[0]["tools"])
    assert "没有勾选「领星MCP」" in unchecked.requests[0]["messages"][0]["content"]
    assert repo.steps[0]["status"] == "invalid"  # 未勾选时领星工具不存在，直接调用被拒绝


def test_runner_explains_when_lingxing_cannot_be_used(server):
    llm = ScriptedLlm([reply(content="无法查询领星")])
    run_agent(ctx(amz="self"), lx.tools_for, llm)
    assert "全部数据" in llm.requests[0]["messages"][0]["content"]

    def broken(context):
        raise lx.McpError("无法连接领星 MCP：ConnectError")
    llm = ScriptedLlm([reply(content="领星暂时连不上")])
    run_agent(ctx(), broken, llm)
    assert "连接领星失败" in llm.requests[0]["messages"][0]["content"]
