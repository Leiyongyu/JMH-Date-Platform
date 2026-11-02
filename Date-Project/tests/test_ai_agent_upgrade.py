"""数据助手升级：数字核对、calculate、知识工具、流式解析、难度路由、上下文压缩、记忆确认、会话摘要、定时简报。"""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime

import httpx
import pytest

from backend.agent import briefs, grounding, llm as llm_module, routing, runner as runner_module, summary
from backend.agent.llm import AgentChatClient, LlmProvider
from backend.agent.tools.base import Tool, ToolResult
from backend.agent.tools.compute import CalculateArgs, CalculationError, calculate
from backend.agent.tools.knowledge import DocIndex, METRICS, MetricArgs, metric_definitions
from tests.test_ai_agent import FakeConversations, FakeRepo, SalesArgs, ScriptedLlm, call, context, reply, run


def month_tool():
    def handler(ctx, args):
        rows = [
            {"month": "2026-09", "group": "A", "sales": 1000.0, "margin": 0.10},
            {"month": "2026-09", "group": "B", "sales": 3000.0, "margin": 0.20},
            {"month": "2026-10", "group": "A", "sales": 1500.0, "margin": 0.125},
            {"month": "2026-10", "group": "B", "sales": 2500.0, "margin": 0.18},
        ]
        return ToolResult(title="月度销售", summary={"合计": 8000.0},
                          columns=[("month", "月份"), ("group", "组别"), ("sales", "净销售额"), ("margin", "毛利率")],
                          rows=rows, source="测试", period=args.month)
    return Tool("sales", "测试", SalesArgs, handler, permission="finance:salesDashboard:list")


# ---------------------------------------------------------------- 数字核对

def test_grounding_matches_rounded_amounts_percent_and_skips_dates_codes():
    results = [{"summary": {"净销售额": 3565926.72, "毛利率": 0.158}, "rows": [{"v": 1234}], "rowCount": 1}]
    answer = ("2026年10月净销售额 3,565,926.72 元（约 356.59 万），毛利率 15.80%，SKU DAS-10071-0040 共 1234 件，"
              "排名前 5，见 [[表:1]]。")
    check = grounding.verify(answer, results, "10月怎么样")
    assert check.status == "passed" and check.checked >= 4


def test_grounding_flags_unknown_numbers_but_ignores_numbers_in_question():
    results = [{"summary": {"净销售额": 3565926.72}, "rows": [], "rowCount": 0}]
    check = grounding.verify("净销售额 3,565,926.72，环比下降 4.7%，目标 5000", results, "目标是5000吗")
    assert check.status == "warned" and check.unmatched == ["4.7%"]
    assert grounding.verify("你好", [], "").status == "skipped"


# ---------------------------------------------------------------- calculate

def stored(tool_result, result_id=1):
    return {"tool": "sales", **tool_result.for_storage(result_id)}


def test_calculate_period_compare_uses_percentage_points_for_ratio_columns():
    results = [stored(month_tool().handler(None, SalesArgs(month="2026-10")))]
    out = calculate(results, CalculateArgs(operation="period_compare", result_id=1, value_columns=["净销售额", "毛利率"],
                                           key_column="组别", period_column="月份",
                                           base_period="2026-09", target_period="2026-10"))
    a = next(row for row in out.rows if row["key"] == "A")
    assert a["sales__diff"] == 500.0 and a["sales__rate"] == 0.5
    assert a["margin__diff"] == 2.5  # 10% → 12.5% = 2.5 个百分点


def test_calculate_share_rank_sum_and_errors():
    results = [stored(month_tool().handler(None, SalesArgs(month="2026-10")))]
    share = calculate(results, CalculateArgs(operation="share", result_id=1, value_columns=["sales"], key_column="组别"))
    assert sum(row["sales__share"] for row in share.rows) == pytest.approx(1.0)
    rank = calculate(results, CalculateArgs(operation="rank", result_id=1, value_columns=["净销售额"], key_column="月份"))
    assert rank.rows[0]["sales"] == 3000.0
    total = calculate(results, CalculateArgs(operation="sum", result_id=1, value_columns=["净销售额"]))
    assert total.rows == [{"sales": 8000.0}]
    with pytest.raises(CalculationError, match="可用列"):
        calculate(results, CalculateArgs(operation="sum", result_id=1, value_columns=["不存在"]))
    with pytest.raises(CalculationError, match="不存在结果编号"):
        calculate(results, CalculateArgs(operation="sum", result_id=9, value_columns=["sales"]))


# ---------------------------------------------------------------- 知识工具

def test_metric_definitions_filter_by_keyword():
    out = metric_definitions(context(), MetricArgs(keyword="毛利率"))
    assert out.rows and all("毛利率" in r["name"] or "毛利率" in r["definition"] for r in out.rows)
    assert len(metric_definitions(context(), MetricArgs()).rows) == len(METRICS)


def test_doc_search_ranks_relevant_chunk_and_drops_secret_lines(tmp_path, monkeypatch):
    from backend.agent.tools import knowledge
    monkeypatch.setattr(knowledge, "REPO_ROOT", tmp_path)
    doc = tmp_path / "guide.md"
    doc.write_text("# 负责人映射表导入\n在绩效页面点击导入按钮上传映射表。\nDB_PASSWORD=abc123\n"
                   "# 库存\n库存健康率说明。\n", encoding="utf-8")
    index = DocIndex([doc])
    hits = index.search("映射表怎么导入")
    assert hits and hits[0][1].heading == "负责人映射表导入"
    assert all("abc123" not in chunk.text for _, chunk in index.search("PASSWORD abc123"))


# ---------------------------------------------------------------- 流式解析

def test_stream_parses_reasoning_content_and_tool_call_fragments(monkeypatch):
    chunks = [
        {"model": "m", "choices": [{"delta": {"reasoning_content": "先想"}}]},
        {"choices": [{"delta": {"reasoning_content": "一下"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "sales", "arguments": "{\"mo"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "nth\":\"2026-10\"}"}}]}}]},
        {"choices": [{"delta": {"content": "好"}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}},
    ]
    body = "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    captured = {}

    def handler(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"})

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_module.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    deltas = []

    async def on_delta(reasoning, content):
        deltas.append((reasoning, content))

    provider = LlmProvider("dashscope", "百炼", "k", "https://x", "qwen", "DASHSCOPE_API_KEY")
    client = AgentChatClient(provider=provider, stream=True)
    result = asyncio.run(client.complete([{"role": "user", "content": "hi"}], thinking=False, model="lite",
                                         on_delta=on_delta))
    assert captured["payload"]["stream"] is True and captured["payload"]["model"] == "lite"
    assert captured["payload"]["enable_thinking"] is False
    assert result.reasoning_content == "先想一下" and result.content == "好"
    assert result.tool_calls[0]["function"] == {"name": "sales", "arguments": "{\"month\":\"2026-10\"}"}
    assert result.usage["totalTokens"] == 10 and deltas[-1] == ("先想一下", "好")


# ---------------------------------------------------------------- 难度路由

def test_routing_turns_thinking_off_only_for_short_non_data_text(monkeypatch):
    monkeypatch.setattr(routing, "settings", replace(routing.settings, ai_agent_thinking_mode="auto",
                                                     ai_agent_thinking_enabled=True, ai_agent_simple_model="lite"))
    assert routing.choose("谢谢") == routing.Route(True, False, "lite")
    assert routing.choose("10月毛利多少").thinking is True
    monkeypatch.setattr(routing, "settings", replace(routing.settings, ai_agent_thinking_mode="on"))
    assert routing.choose("谢谢").thinking is True


# ---------------------------------------------------------------- 运行器集成

def test_results_are_numbered_and_answer_table_refs_expand_in_history():
    llm = ScriptedLlm([
        reply(tool_calls=[call("a", "sales", month="2026-10")]),
        reply(content="10月合计 8,000.00。\n[[表:1]]"),
    ])
    repo, conversations = FakeRepo(), FakeConversations()
    result = run(runner_module.AgentRunner(llm=llm, tools=[month_tool()], repo=repo, conversations=conversations))
    tool_message = json.loads(llm.requests[1]["messages"][3]["content"])
    assert tool_message["result_id"] == 1 and tool_message["table_ref"] == "[[表:1]]"
    assert repo.updates[-1]["results_json"][0]["id"] == 1
    assert result["answer"].endswith("[[表:1]]")  # 运行记录保留引用，页面渲染后端表格
    saved_answer = conversations.appended[-1][1]
    assert "| 月份 | 组别 | 净销售额 | 毛利率 |" in saved_answer and "[[表:" not in saved_answer
    assert result["verification"]["status"] == "passed"


def test_unmatched_numbers_get_one_repair_round_with_calculate():
    llm = ScriptedLlm([
        reply(tool_calls=[call("a", "sales", month="2026-10")]),
        reply(content="A 组环比增长 47.3%。"),
        reply(tool_calls=[call("c", "calculate", operation="period_compare", result_id=1, value_columns=["净销售额"],
                               key_column="组别", period_column="月份", base_period="2026-09",
                               target_period="2026-10")]),
        reply(content="A 组净销售额 1,500.00，比 9 月增加 500.00（50.00%）。"),
    ])
    repo = FakeRepo()
    result = run(runner_module.AgentRunner(llm=llm, tools=[month_tool()], repo=repo, conversations=FakeConversations()))
    repair_prompt = llm.requests[2]["messages"][-1]["content"]
    assert "47.3%" in repair_prompt and "calculate" in repair_prompt
    assert llm.requests[2]["tools"]  # 修正轮仍可调用工具
    assert [s["tool"] for s in repo.steps] == ["sales", "calculate"] and repo.steps[1]["status"] == "completed"
    assert result["verification"] == {"status": "passed", "checked": 3, "unmatched": [], "repaired": True}


def test_still_unmatched_after_repair_is_reported_not_retried_forever():
    llm = ScriptedLlm([
        reply(tool_calls=[call("a", "sales", month="2026-10")]),
        reply(content="增长 47.3%。"),
        reply(content="增长 47.4%。"),
    ])
    result = run(runner_module.AgentRunner(llm=llm, tools=[month_tool()], repo=FakeRepo(),
                                           conversations=FakeConversations()))
    assert result["verification"]["status"] == "warned" and result["verification"]["repaired"] is True
    assert result["answer"] == "增长 47.4%。" and not llm.replies


def test_calculate_with_bad_reference_goes_back_to_model():
    llm = ScriptedLlm([
        reply(tool_calls=[call("c", "calculate", operation="sum", result_id=3, value_columns=["x"])]),
        reply(content="没有数据"),
    ])
    repo = FakeRepo()
    run(runner_module.AgentRunner(llm=llm, tools=[month_tool()], repo=repo, conversations=FakeConversations()))
    assert repo.steps[0]["status"] == "invalid"
    assert "不存在结果编号" in llm.requests[1]["messages"][3]["content"]


def test_context_compaction_replaces_old_tool_results_with_summary(monkeypatch):
    monkeypatch.setattr(runner_module, "settings", replace(runner_module.settings, ai_agent_context_chars=1500))
    llm = ScriptedLlm([
        reply(tool_calls=[call("a", "sales", month="2026-09")]),
        reply(tool_calls=[call("b", "sales", month="2026-10")]),
        reply(content="完成"),
    ])
    run(runner_module.AgentRunner(llm=llm, tools=[month_tool()], repo=FakeRepo(), conversations=FakeConversations()))
    last = llm.requests[2]["messages"]
    tools = [json.loads(m["content"]) for m in last if m["role"] == "tool"]
    assert "rows_omitted" in tools[0] and tools[0]["result_id"] == 1
    assert "rows" in tools[1]  # 最近一轮保持完整


def test_routing_and_streaming_options_are_passed_to_model():
    llm = ScriptedLlm([reply(content="不客气")])
    run(runner_module.AgentRunner(llm=llm, tools=[], repo=FakeRepo(), conversations=FakeConversations()),
        question="谢谢")
    options = llm.requests[0]["options"]
    assert set(options) >= {"thinking", "model", "on_delta"} and callable(options["on_delta"])


def test_streaming_callback_saves_draft_throttled(monkeypatch):
    repo = FakeRepo()
    agent = runner_module.AgentRunner(llm=ScriptedLlm([]), tools=[], repo=repo, conversations=FakeConversations())
    state = runner_module.RunState("run-1")
    on_delta = agent._stream_callback(state, 1)

    async def feed():
        await on_delta("思考", "")
        await on_delta("思考中", "部分回答")  # 间隔太短，不写库
    asyncio.run(feed())
    assert len(repo.updates) == 1 and state.draft == "部分回答"
    assert state.thinking == [{"round": 1, "content": "思考中"}]


def test_inferred_memory_is_pending_until_confirmed():
    llm = ScriptedLlm([
        reply(tool_calls=[call("m", "save_memory", content="用户常看德国站", category="preference")]),
        reply(content="好的"),
    ])
    repo = FakeRepo()
    run(runner_module.AgentRunner(llm=llm, tools=[], repo=repo, conversations=FakeConversations()))
    assert repo.saved_status == "pending"
    assert "确认后生效" in llm.requests[1]["messages"][3]["content"]


def test_expand_table_refs_drops_unknown_and_limits_rows():
    results = [{"columns": [{"key": "k", "label": "名称"}], "rows": [{"k": f"r{i}"} for i in range(25)], "rowCount": 25}]
    text = runner_module.expand_table_refs("看 [[表:1]] 和 [[表:5]]", results)
    assert "| r19 |" in text and "| r20 |" not in text and "共25行" in text and "[[表:5]]" not in text


# ---------------------------------------------------------------- 会话摘要

class SummaryConversations(FakeConversations):
    def __init__(self, count, covered=0):
        super().__init__()
        self.state = {"messageCount": count, "summary": "旧摘要", "summaryMessageCount": covered}
        self.saved = None

    def summary_state(self, user_id, conversation_uuid):
        return self.state

    def messages_range(self, user_id, conversation_uuid, offset, limit):
        return [{"role": "user", "content": f"问题{offset + i}"} for i in range(limit)]

    def save_summary(self, user_id, conversation_uuid, text, covered):
        self.saved = (text, covered)


def test_summary_waits_for_a_batch_then_merges_previous_summary():
    llm = ScriptedLlm([reply(content="新摘要")])
    few = SummaryConversations(count=12 + summary.SUMMARY_BATCH - 1)
    assert asyncio.run(summary.refresh_summary(llm, few, 1, "c", keep_recent=12)) is False
    enough = SummaryConversations(count=12 + summary.SUMMARY_BATCH)
    assert asyncio.run(summary.refresh_summary(llm, enough, 1, "c", keep_recent=12)) is True
    assert enough.saved == ("新摘要", summary.SUMMARY_BATCH)
    request = llm.requests[0]
    assert "旧摘要" in request["messages"][1]["content"] and request["options"]["thinking"] is False


def test_summary_is_included_in_system_prompt():
    from backend.agent.prompts import build_system_prompt
    prompt = build_system_prompt(context(), [], [], None, "用户关注 10 月德国站")
    assert "较早内容的摘要" in prompt and "德国站" in prompt


# ---------------------------------------------------------------- 定时简报

@pytest.mark.parametrize("frequency,weekday,day,after,expected", [
    ("daily", None, None, datetime(2026, 11, 2, 8, 30), datetime(2026, 11, 2, 9)),
    ("daily", None, None, datetime(2026, 11, 2, 9, 0), datetime(2026, 11, 3, 9)),
    ("weekly", 1, None, datetime(2026, 11, 2, 10), datetime(2026, 11, 9, 9)),  # 11-02 是周一
    ("weekly", 5, None, datetime(2026, 11, 2, 10), datetime(2026, 11, 6, 9)),
    ("monthly", None, 1, datetime(2026, 12, 15), datetime(2027, 1, 1, 9)),
    ("monthly", None, 28, datetime(2026, 2, 3), datetime(2026, 2, 28, 9)),
])
def test_next_run(frequency, weekday, day, after, expected):
    assert briefs.next_run(frequency, weekday, day, 9, after) == expected


def test_brief_request_requires_weekday_or_day():
    with pytest.raises(ValueError):
        briefs.BriefRequest(title="周报", question="上周销售", frequency="weekly")
    assert briefs.BriefRequest(title="月报", question="上月销售", frequency="monthly", month_day=1).run_hour == 9


def test_scheduled_brief_skips_when_already_claimed(monkeypatch):
    brief = {"id": 3, "frequency": "daily", "weekday": None, "monthDay": None, "runHour": 9, "title": "日报",
             "question": "昨天销售", "conversationId": None}
    monkeypatch.setattr(briefs.runs_repo, "get_brief", lambda user_id, brief_id: brief)
    monkeypatch.setattr(briefs.runs_repo, "claim_brief", lambda *args: False)
    assert asyncio.run(briefs.run_brief(context(), 3, force=False)) == {"briefId": 3, "skipped": True}


# ---------------------------------------------------------------- 评测集

def test_eval_cases_reference_existing_tools_and_check_rules():
    from backend.agent import evaluate
    from backend.agent.tools.business import BUSINESS_TOOLS
    from backend.agent.tools.knowledge import KNOWLEDGE_TOOLS
    names = {t.name for t in [*BUSINESS_TOOLS, *KNOWLEDGE_TOOLS]} | {"calculate"}
    cases = evaluate.load_cases(evaluate.CASES_FILE, None)
    assert len({c["id"] for c in cases}) == len(cases) >= 10
    for case in cases:
        for key in ("expect_tools", "expect_all_tools", "expect_any_tools", "forbid_tools"):
            assert set(case.get(key) or []) <= names, (case["id"], key)
    case = {"expect_tools": ["sales"], "forbid_tools": ["x"], "answer_contains": [["来源"]]}
    assert evaluate.check(case, "completed", ["sales"], "结论。来源：测试", {"status": "passed"}) == []
    problems = evaluate.check(case, "completed", ["x"], "结论", {"status": "warned", "unmatched": ["4.7%"]})
    assert len(problems) == 4
