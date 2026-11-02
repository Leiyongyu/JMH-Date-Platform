from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field

from backend.agent import runner as runner_module
from backend.agent.context import SCOPE_EBAY, AgentAccess, AgentContext
from backend.agent.llm import LlmError, LlmReply
from backend.agent.tools import business
from backend.agent.tools.base import MODEL_ROW_LIMIT, Tool, ToolResult


# ---------------------------------------------------------------- 测试替身

def call(call_id, name, **arguments):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


def reply(content="", tool_calls=None, reasoning=None):
    return LlmReply(content=content, reasoning_content=reasoning, tool_calls=tool_calls or [],
                    model="test-model", finish_reason="stop",
                    usage={"promptTokens": 10, "completionTokens": 5, "totalTokens": 15})


class ScriptedLlm:
    """按顺序返回预设回复，并记录每次请求（含是否带 tools）。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    async def complete(self, messages, tools=None, *, tool_choice=None, request_id=""):
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeRepo:
    def __init__(self, memories=None):
        self.updates = []
        self.steps = []
        self.memories = list(memories or [])
        self.saved = []
        self.deleted = []

    def list_memories(self, user_id):
        return self.memories

    def update_run(self, run_id, **fields):
        self.updates.append(fields)

    def insert_step(self, run_id, seq, round_no, tool, arguments, status, rows, duration, error):
        self.steps.append(dict(seq=seq, round=round_no, tool=tool, arguments=arguments, status=status,
                               rows=rows, error=error))

    def save_memory(self, user_id, category, content, run_id):
        self.saved.append((user_id, category, content))
        return 7

    def delete_memory(self, user_id, memory_id):
        self.deleted.append((user_id, memory_id))
        return True


class FakeConversations:
    def __init__(self, history=None):
        self.history = history or []
        self.appended = []

    def context_messages(self, user_id, conversation_uuid, limit):
        return self.history

    def append_message(self, user_id, username, conversation_uuid, role, content, **kwargs):
        self.appended.append((role, content, kwargs.get("is_error", False)))
        return len(self.appended)


class SalesArgs(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")


def sales_tool(rows=3, permission="finance:salesDashboard:list", name="sales"):
    def handler(context, args):
        return ToolResult(title=f"{args.month} sales", summary={"合计": rows},
                          columns=[("k", "名称"), ("v", "值")],
                          rows=[{"k": f"r{i}", "v": i} for i in range(rows)], source="测试", period=args.month)
    return Tool(name, "测试工具", SalesArgs, handler, permission=permission)


def context(permissions=("finance:salesDashboard:list",), scopes=None):
    return AgentContext(user_id=1, username="tester",
                        access=AgentAccess(frozenset(permissions), scopes or {}), request_id="req-1")


def run(runner, ctx=None, question="10月销售怎么样"):
    return asyncio.run(runner.run("run-1", ctx or context(), "conv-1", question, {"title": "首页"}))


# ---------------------------------------------------------------- 编排主流程

def test_plan_parallel_tools_then_answer():
    llm = ScriptedLlm([
        reply(tool_calls=[call("p1", "update_plan", steps=[
            {"title": "查询9月", "status": "in_progress"}, {"title": "查询10月", "status": "pending"}])],
            reasoning="先规划"),
        reply(tool_calls=[call("a", "sales", month="2026-09"), call("b", "sales", month="2026-10")]),
        reply(content="10月比9月好。来源：测试"),
    ])
    repo, conversations = FakeRepo(), FakeConversations([{"role": "user", "content": "上一个问题"}])
    result = run(runner_module.AgentRunner(llm=llm, tools=[sales_tool()], repo=repo,
                                           conversations=conversations))

    assert result == {"status": "completed", "answer": "10月比9月好。来源：测试"}
    # 两个独立查询在同一轮并行完成，各记一条调用日志
    assert [(s["seq"], s["round"], s["arguments"]["month"], s["status"]) for s in repo.steps] == [
        (1, 2, "2026-09", "completed"), (2, 2, "2026-10", "completed")]
    final = repo.updates[-1]
    assert final["status"] == "completed" and final["tool_calls"] == 2 and final["rounds"] == 3
    assert [step["status"] for step in final["plan_json"]] == ["completed", "pending"]
    assert [r["period"] for r in final["results_json"]] == ["2026-09", "2026-10"]
    assert [(role, err) for role, _c, err in conversations.appended] == [("user", False), ("assistant", False)]
    # 思考内容随 assistant 消息原样回传；历史以摘要进入系统提示，而非 assistant 消息
    second = llm.requests[1]["messages"]
    assert second[2]["reasoning_content"] == "先规划"
    assert "上一个问题" in second[0]["content"] and second[0]["role"] == "system"
    tool_messages = [m for m in llm.requests[2]["messages"] if m["role"] == "tool"]
    assert {m["tool_call_id"] for m in tool_messages} == {"p1", "a", "b"}


def test_permission_denied_and_invalid_arguments_go_back_to_model():
    llm = ScriptedLlm([
        reply(tool_calls=[call("a", "sales", month="2026-10"), call("b", "sales", month="10月")]),
        reply(content="缺少权限"),
    ])
    repo = FakeRepo()
    runner = runner_module.AgentRunner(llm=llm, tools=[sales_tool(permission="finance:secret:list")],
                                       repo=repo, conversations=FakeConversations())
    # 没有该工具权限时连工具定义都不提供给模型；即使模型硬调也会被拒绝
    run(runner)
    assert all(t["function"]["name"] != "sales" for t in llm.requests[0]["tools"])
    statuses = {s["arguments"]["month"] if s["arguments"] else None: s["status"] for s in repo.steps}
    assert statuses == {None: "invalid", "2026-10": "denied"}
    tool_contents = [json.loads(m["content"]) for m in llm.requests[1]["messages"] if m["role"] == "tool"]
    assert any("权限" in c["error"] for c in tool_contents)


def test_budget_exhaustion_forces_answer_without_tools(monkeypatch):
    monkeypatch.setattr(runner_module, "settings", replace(runner_module.settings, ai_agent_max_tool_calls=2))
    llm = ScriptedLlm([
        reply(tool_calls=[call("a", "sales", month="2026-08"), call("b", "sales", month="2026-09"),
                          call("c", "sales", month="2026-10")]),
        reply(content="已基于已有结果回答"),
    ])
    repo = FakeRepo()
    run(runner_module.AgentRunner(llm=llm, tools=[sales_tool()], repo=repo, conversations=FakeConversations()))
    assert [s["status"] for s in repo.steps] == ["completed", "completed", "invalid"]
    last = llm.requests[-1]
    assert last["tools"] is None
    assert last["messages"][-1]["role"] == "system" and "不要再调用工具" in last["messages"][-1]["content"]


def test_unknown_tool_and_too_many_calls_are_rejected():
    calls = [call(f"c{i}", "sales", month="2026-10") for i in range(7)] + [call("x", "drop_table")]
    llm = ScriptedLlm([reply(tool_calls=calls), reply(content="ok")])
    repo = FakeRepo()
    run(runner_module.AgentRunner(llm=llm, tools=[sales_tool()], repo=repo, conversations=FakeConversations()))
    assert [s["status"] for s in repo.steps].count("completed") == runner_module.MAX_CALLS_PER_ROUND
    assert repo.steps[-1]["tool"] == "drop_table" and repo.steps[-1]["status"] == "invalid"


def test_memory_tools_and_memories_in_prompt():
    llm = ScriptedLlm([
        reply(tool_calls=[call("m1", "save_memory", content="用户默认看德国站", category="preference"),
                          call("m2", "forget_memory", memory_id=3)]),
        reply(content="已记住"),
    ])
    repo = FakeRepo(memories=[{"id": 3, "category": "fact", "content": "旧的偏好"}])
    run(runner_module.AgentRunner(llm=llm, tools=[sales_tool()], repo=repo, conversations=FakeConversations()),
        question="以后默认看德国站，忘掉旧的偏好")
    assert repo.saved == [(1, "preference", "用户默认看德国站")]
    assert repo.deleted == [(1, 3)]
    assert "#3（fact）旧的偏好" in llm.requests[0]["messages"][0]["content"]
    assert repo.steps == []  # 元工具不计入业务调用日志


def test_llm_failure_marks_run_failed_and_saves_error_message():
    conversations = FakeConversations()
    repo = FakeRepo()
    result = run(runner_module.AgentRunner(llm=ScriptedLlm([LlmError("DeepSeek账户余额不足")]),
                                           tools=[sales_tool()], repo=repo, conversations=conversations))
    assert result == {"status": "failed", "error": "DeepSeek账户余额不足"}
    assert repo.updates[-1]["status"] == "failed"
    assert conversations.appended[-1] == ("assistant", "DeepSeek账户余额不足", True)


def test_tool_crash_is_hidden_from_model(monkeypatch):
    def boom(context, args):
        raise RuntimeError("Access denied for user root password=secret")
    tool = Tool("sales", "x", SalesArgs, boom)
    llm = ScriptedLlm([reply(tool_calls=[call("a", "sales", month="2026-10")]), reply(content="失败了")])
    repo = FakeRepo()
    run(runner_module.AgentRunner(llm=llm, tools=[tool], repo=repo, conversations=FakeConversations()))
    content = next(m["content"] for m in llm.requests[1]["messages"] if m["role"] == "tool")
    assert "secret" not in content and "服务端错误" in content
    assert repo.steps[0]["status"] == "failed"


# ---------------------------------------------------------------- 权限与结果

def test_access_payload_parsing_and_admin():
    access = AgentAccess.from_payload({"permissions": ["a:b:c", " "],
                                       "scopes": {SCOPE_EBAY: ["张三", "张三", " "], "unknown": None}})
    assert access.has("a:b:c") and not access.has("x:y:z")
    assert access.scope(SCOPE_EBAY) == ["张三"]
    assert access.scope("operations:amzReplenishment") == []  # 未下发的模块按无数据处理
    admin = AgentAccess.from_payload({"permissions": ["*:*:*"]})
    assert admin.has("anything") and admin.scope(SCOPE_EBAY) is None


def test_tool_result_truncates_rows_for_model_only():
    result = ToolResult(title="t", columns=[("k", "名称")], rows=[{"k": i} for i in range(MODEL_ROW_LIMIT + 5)])
    payload = json.loads(result.for_model())
    assert len(payload["rows"]) == MODEL_ROW_LIMIT and payload["row_count"] == MODEL_ROW_LIMIT + 5
    assert "rows_truncated" in payload
    assert len(result.for_storage()["rows"]) == MODEL_ROW_LIMIT + 5


def test_performance_ranking_tool_summarizes_unassigned(monkeypatch):
    from backend.services import performance_service
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {"stat_month": "2026-10", "partial": True, "pagination": {"total": 3},
                "items": [{"principalNames": "杨萍", "grossProfit": "133301.32", "netSalesAmount": "1"},
                          {"principalNames": "未分配", "grossProfit": "119773.555867", "netSalesAmount": "2"}]}

    monkeypatch.setattr(performance_service, "list_performance_rankings", fake)
    result = business.performance_ranking(context(), business.PerformanceArgs(top=1))
    assert captured["page_size"] == 1000 and captured["platform"] == "combined"
    # 合计与未分配按全部负责人计算，即使未分配不在前 N 名里
    assert [r["principal"] for r in result.rows] == ["杨萍"]
    assert result.summary["未分配毛利润"] == 119773.56 and result.summary["合计毛利润"] == 253074.88
    assert any("部分数据" in note for note in result.notes) and any("前1名" in note for note in result.notes)


def test_replenishment_tool_applies_data_scope(monkeypatch):
    from backend.services import ebay_replenishment_v2_service as service
    calls = []
    monkeypatch.setattr(service, "list_replenishment", lambda **kw: calls.append(kw) or {
        "items": [{"sku": "A-1", "profit_rate": "0.123456"}], "pagination": {"total": 1}})
    scoped = context(("operations:ebayReplenishmentV2:list",), {SCOPE_EBAY: ["张三"]})
    result = business.ebay_replenishment(scoped, business.ReplenishmentArgs())
    assert calls[0]["allowed_principals"] == ["张三"] and result.rows[0]["profit_rate"] == 0.1235
    assert any("数据范围" in note for note in result.notes)
    none_scope = context(("operations:ebayReplenishmentV2:list",), {SCOPE_EBAY: []})
    assert business.ebay_replenishment(none_scope, business.ReplenishmentArgs()).rows == []
    assert len(calls) == 1  # 没有数据范围时不查询


def test_every_business_tool_schema_is_valid_json_schema():
    for tool in business.BUSINESS_TOOLS:
        schema = tool.schema()["function"]["parameters"]
        assert schema["type"] == "object" and "$defs" not in json.dumps(schema)
        assert tool.permission is None or tool.permission.endswith(":list")


# ---------------------------------------------------------------- 接口

def test_agent_run_api_requires_owned_conversation_and_returns_run_id(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import deps
    from backend.api.v1 import ai_assistant as api
    from backend.agent import runner
    from backend.repositories import ai_agent_repository

    monkeypatch.setattr(deps, "settings", SimpleNamespace(python_internal_api_token="t"))
    from backend.agent import llm
    monkeypatch.setattr(llm, "settings", replace(llm.settings, ai_agent_provider="deepseek", deepseek_api_key="k"))
    monkeypatch.setattr(api.ai_assistant_service, "get_conversation", lambda uid, cid: {"id": cid})
    started = {}

    async def fake_start(ctx, conversation_id, message, page):
        started.update(ctx=ctx, conversation=conversation_id, message=message)
        return "11111111-1111-1111-1111-111111111111"

    monkeypatch.setattr(runner, "start_run", fake_start)
    monkeypatch.setattr(ai_agent_repository, "get_run", lambda uid, rid: None if uid != 1 else {"runId": rid})
    app = FastAPI()

    @app.middleware("http")
    async def trace(request, call_next):
        request.state.request_id = "req"
        return await call_next(request)

    app.include_router(api.router)
    headers = {"X-Internal-Token": "t", "X-Erp-User-ID": "1", "X-Erp-User": "tester"}
    with TestClient(app) as client:
        body = {"conversation_id": "22222222-2222-2222-2222-222222222222", "message": "10月排名",
                "access": {"permissions": ["finance:performanceRanking:list"], "scopes": {}}}
        response = client.post("/api/v1/ai-assistant/agent-runs", json=body, headers=headers)
        assert response.status_code == 202
        assert response.json()["data"]["runId"] == "11111111-1111-1111-1111-111111111111"
        assert started["ctx"].access.has("finance:performanceRanking:list")
        run_url = "/api/v1/ai-assistant/agent-runs/11111111-1111-1111-1111-111111111111"
        assert client.get(run_url, headers=headers).status_code == 200
        assert client.get(run_url, headers={**headers, "X-Erp-User-ID": "2"}).status_code == 404
        assert client.post("/api/v1/ai-assistant/agent-runs", json=body).status_code == 401


def test_thinking_is_saved_per_round_and_truncated():
    long_thought = "想" * (runner_module.THINKING_CHARS + 10)
    llm = ScriptedLlm([
        reply(tool_calls=[call("a", "sales", month="2026-10")], reasoning="先查10月"),
        reply(content="结论", reasoning=long_thought),
    ])
    repo = FakeRepo()
    run(runner_module.AgentRunner(llm=llm, tools=[sales_tool()], repo=repo, conversations=FakeConversations()))
    thinking = repo.updates[-1]["thinking_json"]
    assert [item["round"] for item in thinking] == [1, 2]
    assert thinking[0]["content"] == "先查10月"
    assert thinking[1]["content"].endswith("（已截断）")
    # 思考内容在每轮结束时就落库，前端轮询能实时看到
    assert any(update.get("thinking_json") for update in repo.updates[:-1])
    # 完整思考仍原样回传给模型（截断只影响保存）
    assert llm.requests[1]["messages"][2]["reasoning_content"] == "先查10月"


# ---------------------------------------------------------------- 模型提供方

def test_provider_switch_and_thinking_parameters(monkeypatch):
    from backend.agent import llm
    base = replace(llm.settings, dashscope_api_key=" sk-test ", deepseek_api_key="ds",
                   dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/",
                   dashscope_model="qwen3.7-max-2026-06-08")
    monkeypatch.setattr(llm, "settings", replace(base, ai_agent_provider="dashscope"))
    qwen = llm.current_provider()
    assert (qwen.name, qwen.model, qwen.api_key, qwen.key_env) == (
        "dashscope", "qwen3.7-max-2026-06-08", "sk-test", "DASHSCOPE_API_KEY")
    assert qwen.base_url.endswith("/compatible-mode/v1")
    assert qwen.thinking_fields(True) == {"enable_thinking": True}
    monkeypatch.setattr(llm, "settings", replace(base, ai_agent_provider="deepseek"))
    assert llm.current_provider().thinking_fields(False) == {"thinking": {"type": "disabled"}}
    monkeypatch.setattr(llm, "settings", replace(base, ai_agent_provider="unknown"))
    assert llm.current_provider().name == "deepseek"


def test_dashscope_request_payload_and_error_mapping(monkeypatch):
    import httpx
    from backend.agent import llm
    sent = {}

    def handler(request):
        sent["url"] = str(request.url)
        sent["auth"] = request.headers["Authorization"]
        sent["body"] = json.loads(request.content)
        if sent["body"]["messages"][0]["content"] == "fail":
            return httpx.Response(401, json={"error": {"message": "Invalid API-key"}})
        return httpx.Response(200, json={"model": "qwen3.7-max-2026-06-08", "choices": [{
            "finish_reason": "tool_calls",
            "message": {"content": "", "reasoning_content": "想一想",
                        "tool_calls": [{"id": "c1", "type": "function",
                                        "function": {"name": "sales", "arguments": "{}"}}]}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    provider = llm.LlmProvider("dashscope", "阿里云百炼", "sk-test",
                               "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.7-max-2026-06-08",
                               "DASHSCOPE_API_KEY")
    client = llm.AgentChatClient(thinking=True, provider=provider)
    result = asyncio.run(client.complete([{"role": "user", "content": "hi"}], [{"type": "function"}]))
    assert sent["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert sent["auth"] == "Bearer sk-test"
    assert sent["body"]["enable_thinking"] is True and "thinking" not in sent["body"]
    assert sent["body"]["model"] == "qwen3.7-max-2026-06-08" and sent["body"]["stream"] is False
    assert result.reasoning_content == "想一想" and result.tool_calls[0]["id"] == "c1"
    assert result.as_message()["reasoning_content"] == "想一想"
    with pytest.raises(LlmError, match="阿里云百炼 API Key无效.*DASHSCOPE_API_KEY"):
        asyncio.run(client.complete([{"role": "user", "content": "fail"}]))
    with pytest.raises(LlmError, match="DASHSCOPE_API_KEY"):
        asyncio.run(llm.AgentChatClient(provider=replace(provider, api_key="")).complete([]))


def test_status_reports_active_provider(monkeypatch):
    from backend.agent import llm
    from backend.services.ai_assistant_service import AiAssistantService
    monkeypatch.setattr(llm, "settings", replace(llm.settings, ai_agent_provider="dashscope",
                                                 dashscope_api_key="", dashscope_model="qwen3.7-max-2026-06-08"))
    status = AiAssistantService().status()
    assert status["provider"] == "dashscope" and status["configured"] is False
    assert status["model"] == "qwen3.7-max-2026-06-08" and status["keyEnv"] == "DASHSCOPE_API_KEY"
