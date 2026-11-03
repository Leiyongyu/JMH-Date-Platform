"""领星 MCP：协议握手与 SSE 响应、只读白名单、勾选才提供工具、数据范围限制、结果转换。"""
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

REMOTE_TOOLS = [
    {"name": "get_my_sids", "description": "店铺列表", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_fba_stock_list", "description": "FBA库存",
     "inputSchema": {"$schema": "x", "type": "object", "properties": {"sku": {"type": "string"}}}},
    {"name": "put_campaigns_sp", "description": "修改SP广告活动", "inputSchema": {"type": "object"}},
    {"name": "fba_delete_shipment_list", "description": "删除发货单", "inputSchema": {"type": "object"}},
]


class FakeServer:
    """模拟领星 MCP：initialize 返回会话号，tools/list 用 SSE 返回，tools/call 用 JSON 返回。"""

    def __init__(self):
        self.calls: list[dict] = []
        self.keys: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body)
        self.keys.add(request.headers.get("x-mcp-key", ""))
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"capabilities": {}}},
                                  headers={"mcp-session-id": "s1"})
        if method == "notifications/initialized":
            return httpx.Response(202)
        assert request.headers.get("mcp-session-id") == "s1"
        if method == "tools/list":
            event = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"tools": REMOTE_TOOLS}})
            return httpx.Response(200, text=f"event: message\ndata: {event}\n\n",
                                  headers={"content-type": "text/event-stream"})
        payload = {"code": 0, "total": 2, "data": [
            {"sku": "A-1", "available": 120, "nested": {"x": 1}}, {"sku": "B-2", "available": 30, "nested": {}}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}], "isError": False}})


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


def test_only_read_only_tools_are_exposed_and_schema_is_cleaned(server):
    tools = lx.tools_for(ctx())
    assert [t.name for t in tools] == ["lingxing_get_my_sids", "lingxing_get_fba_stock_list"]
    schema = tools[1].schema()["function"]["parameters"]
    assert "$schema" not in schema and schema["properties"]["sku"]["type"] == "string"
    assert server.keys == {"k-123"}
    assert not lx.is_read_only("put_campaigns_sp") and not lx.is_read_only("fba_delete_shipment_list")
    with pytest.raises(lx.McpError, match="白名单"):
        lx.client().call("put_campaigns_sp", {})


def test_tool_call_converts_json_rows_and_skips_nested_fields(server):
    tool = lx.tools_for(ctx())[1]
    result = tool.handler(ctx(), tool.parse({"sku": "A"}))
    assert [c[0] for c in result.columns] == ["sku", "available"]
    assert result.rows[0] == {"sku": "A-1", "available": 120} and result.summary["total"] == 2
    assert server.calls[-1]["params"] == {"name": "get_fba_stock_list", "arguments": {"sku": "A"}}


def test_not_checked_or_limited_scope_or_unconfigured_returns_no_tools(server, monkeypatch):
    assert lx.tools_for(ctx(sources=())) == []
    assert lx.tools_for(ctx(amz="self")) == []
    assert not any(c.get("method") == "tools/list" for c in server.calls)
    monkeypatch.setattr(lx, "settings", replace(lx.settings, lingxing_mcp_key=""))
    assert lx.tools_for(ctx()) == []


def test_error_results_and_text_results():
    with pytest.raises(ValueError, match="领星返回错误"):
        lx.to_tool_result("get_my_sids", {"content": [{"type": "text", "text": "参数sid不能为空"}], "isError": True})
    text = lx.to_tool_result("get_my_sids", {"content": [{"type": "text", "text": "共3个店铺"}]})
    assert text.summary["内容"] == "共3个店铺" and not text.rows


def test_status_codes_map_to_readable_errors():
    def unauthorized(request):
        return httpx.Response(401, json={})
    client = lx.McpClient("https://mcp.test", "bad", transport=httpx.MockTransport(unauthorized))
    with pytest.raises(lx.McpError, match="LINGXING_MCP_KEY"):
        client.list_tools()


def run_agent(context, external, llm):
    repo = FakeRepo()
    agent = runner_module.AgentRunner(llm=llm, tools=[], repo=repo, conversations=FakeConversations(),
                                      external_tools=external)
    asyncio.run(agent.run("run-1", context, "conv-1", "领星FBA库存多少", None))
    return repo


def test_runner_offers_lingxing_tools_only_when_checked(server, monkeypatch):
    monkeypatch.setattr(runner_module.lingxing_mcp, "settings", lx.settings)
    llm = ScriptedLlm([reply(tool_calls=[call("a", "lingxing_get_fba_stock_list", sku="A")]), reply(content="A-1 有 120 件")])
    repo = run_agent(ctx(), lx.tools_for, llm)
    offered = {s["function"]["name"] for s in llm.requests[0]["tools"]}
    assert "lingxing_get_fba_stock_list" in offered
    assert "勾选了「领星MCP」" in llm.requests[0]["messages"][0]["content"]
    assert repo.steps[0]["status"] == "completed"

    unchecked = ScriptedLlm([reply(tool_calls=[call("a", "lingxing_get_fba_stock_list")]), reply(content="请勾选")])
    repo = run_agent(ctx(sources=()), lx.tools_for, unchecked)
    assert not any(s["function"]["name"].startswith("lingxing_") for s in unchecked.requests[0]["tools"])
    assert "没有勾选「领星MCP」" in unchecked.requests[0]["messages"][0]["content"]
    assert repo.steps[0]["status"] == "invalid"  # 未勾选时直接调用领星工具会被拒绝


def test_runner_explains_when_lingxing_cannot_be_used(server):
    llm = ScriptedLlm([reply(content="无法查询领星")])
    run_agent(ctx(amz="self"), lx.tools_for, llm)
    assert "全部数据" in llm.requests[0]["messages"][0]["content"]

    def broken(context):
        raise lx.McpError("无法连接领星 MCP：ConnectError")
    llm = ScriptedLlm([reply(content="领星暂时连不上")])
    run_agent(ctx(), broken, llm)
    assert "连接领星失败" in llm.requests[0]["messages"][0]["content"]
