"""数据助手的任务编排：规划 → 并行调用工具 → 观察结果 → 继续或作答 → 核对数字。

每轮把模型发起的工具调用分三类执行：元工具（计划、记忆）按顺序处理，业务/知识查询并行执行
（受并发上限和单次超时约束），calculate 在本轮查询完成后基于已有结果计算。轮次、调用次数、总时长
三类预算任一用尽，就不再提供工具、要求模型基于已有结果作答。

- 每个工具结果按出现顺序编号（result_id），回答里用 [[表:N]] 引用后端表格，calculate 用编号取数；
- 最终回答里的数字要能在工具结果里找到，找不到时给模型一次修正机会，仍不一致则在页面提示；
- 开启流式时，进行中的思考和回答节流写入 ai_agent_run，前端轮询即可逐段显示；
- 发给模型的上下文超过 AI_AGENT_CONTEXT_CHARS 时，较早的工具结果压缩为汇总（明细仍可按编号引用）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from starlette.concurrency import run_in_threadpool

from backend.agent import grounding, routing
from backend.agent.context import AgentContext, ToolPermissionError
from backend.agent.llm import AgentChatClient, LlmError, LlmReply
from backend.agent.prompts import THINKING_LANGUAGE_HINT, build_system_prompt
from backend.agent.summary import refresh_summary
from backend.agent.tools.base import Tool, ToolArgumentError, ToolResult, _clean_schema
from backend.agent.tools.business import BUSINESS_TOOLS
from backend.agent.tools.compute import CalculateArgs, CalculationError, calculate
from backend.agent.tools.ebay_live_tools import EBAY_LIVE_TOOLS
from backend.agent.tools.knowledge import KNOWLEDGE_TOOLS
from backend.agent.tools.meta import (
    FORGET_MEMORY_TOOL, META_ARGS, META_TOOL_NAMES, PLAN_TOOL, SAVE_MEMORY_TOOL, meta_schemas,
)
from backend.config import settings
from backend.repositories import ai_agent_repository as runs_repo
from backend.repositories.ai_conversation_repository import ai_conversation_repository

LOG = logging.getLogger(__name__)
MAX_CALLS_PER_ROUND = 6
# 单轮思考内容的保存上限（字符）；完整内容仍原样回传给模型。
THINKING_CHARS = 6000
HISTORY_MESSAGES = 12
# 流式输出写库的最小间隔（秒）
STREAM_SAVE_INTERVAL = 0.8
# 回答落入会话记录时，[[表:N]] 展开成 Markdown 表格的最大行数
EXPANDED_TABLE_ROWS = 20
CALCULATE_TOOL = "calculate"
FINAL_INSTRUCTION = "执行预算已用完或已获得足够数据。请不要再调用工具，直接基于上面的工具结果回答用户；未查到的部分如实说明。"
TABLE_REF = re.compile(r"\[\[表:(\d+)\]\]")


@dataclass
class RunState:
    run_id: str
    question: str = ""
    plan: list[dict[str, str]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    thinking: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    seq: int = 0
    # 进行中的回答（流式），完成后由最终回答覆盖
    draft: str = ""
    verification: dict[str, Any] | None = None
    # tool_call_id → (result_id, ToolResult)：上下文压缩时替换为汇总
    tool_messages: dict[str, tuple[int, ToolResult]] = field(default_factory=dict)
    compacted: set[str] = field(default_factory=set)
    last_stream_save: float = 0.0


@dataclass
class CallOutcome:
    call_id: str
    name: str
    content: str
    status: str
    arguments: Any = None
    row_count: int = 0
    duration_ms: int = 0
    error: str | None = None
    result: ToolResult | None = None


def calculate_schema() -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": CALCULATE_TOOL,
        "description": "在本次已查到的工具结果上做精确计算：环比/同比（period_compare）、两次结果对比（compare）、"
                       "占比（share）、排名（rank）、合计（sum）。回答里的差值、变化率、占比必须用它算，不要心算。",
        "parameters": _clean_schema(CalculateArgs.model_json_schema()),
    }}


# 只借用 Tool 的参数解析与报错格式；calculate 由运行器直接执行
_CALCULATE_PARSER = Tool(CALCULATE_TOOL, "", CalculateArgs, lambda context, args: None)


class AgentRunner:
    def __init__(self, llm: AgentChatClient | None = None, tools: list[Tool] | None = None,
                 repo=runs_repo, conversations=ai_conversation_repository):
        self.llm = llm or AgentChatClient()
        default_tools = [*BUSINESS_TOOLS, *KNOWLEDGE_TOOLS, *EBAY_LIVE_TOOLS]
        self.tools = {tool.name: tool for tool in (tools if tools is not None else default_tools)}
        self.repo = repo
        self.conversations = conversations
        self._semaphore = asyncio.Semaphore(max(1, settings.ai_agent_parallel_tools))

    # ------------------------------------------------------------ 入口

    async def run(self, run_id: str, context: AgentContext, conversation_uuid: str,
                  question: str, page: dict[str, str] | None = None, keep_title: bool = False) -> dict[str, Any]:
        state = RunState(run_id, question=question)
        started = time.monotonic()
        try:
            memories = await run_in_threadpool(self.repo.list_memories, context.user_id)
            history = await run_in_threadpool(
                self.conversations.context_messages, context.user_id, conversation_uuid, HISTORY_MESSAGES)
            summary = await run_in_threadpool(
                self.conversations.context_summary, context.user_id, conversation_uuid)
            await run_in_threadpool(
                self.conversations.append_message, context.user_id, context.username, conversation_uuid,
                "user", question, request_id=context.request_id,
                first_message_title=None if keep_title else " ".join(question.split())[:40])
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": build_system_prompt(context, memories, history, page, summary)},
                # 会话记录保存用户原话；发给模型的提问前固定加上思考语言要求。
                {"role": "user", "content": f"{THINKING_LANGUAGE_HINT}{question}"},
            ]
            available = [tool for tool in self.tools.values() if tool.available_to(context)]
            schemas = meta_schemas() + [tool.schema() for tool in available] + [calculate_schema()]
            route = routing.choose(question)
            answer = await self._loop(state, context, messages, schemas, started, route)
        except LlmError as exc:
            return await self._fail(state, context, conversation_uuid, str(exc))
        except Exception:  # 未预期错误：记录详情，对用户只给通用提示。
            LOG.exception("agent run failed run_id=%s", run_id)
            return await self._fail(state, context, conversation_uuid, "数据助手执行失败，请稍后重试")
        outcome = await self._complete(state, context, conversation_uuid, answer)
        await self._refresh_summary(context, conversation_uuid)
        return outcome

    # ------------------------------------------------------------ 主循环

    async def _loop(self, state: RunState, context: AgentContext, messages: list[dict[str, Any]],
                    schemas: list[dict[str, Any]], started: float, route: routing.Route) -> str:
        max_rounds = max(1, settings.ai_agent_max_rounds)
        repaired = False
        for round_no in range(1, max_rounds + 1):
            elapsed = time.monotonic() - started
            exhausted = (
                round_no == max_rounds
                or state.tool_calls >= settings.ai_agent_max_tool_calls
                or elapsed >= settings.ai_agent_timeout_sec * 0.75
            )
            if exhausted:
                messages.append({"role": "system", "content": FINAL_INSTRUCTION})
            self._compact(state, messages)
            reply = await self.llm.complete(
                messages, None if exhausted else schemas, request_id=context.request_id,
                thinking=route.thinking, model=route.model, on_delta=self._stream_callback(state, round_no))
            self._record_reply(state, round_no, reply)
            await self._save_progress(state)
            if not exhausted and reply.tool_calls:
                messages.append(reply.as_message())
                outcomes = await self._execute(state, context, reply.tool_calls, round_no)
                for outcome in outcomes:
                    messages.append({"role": "tool", "tool_call_id": outcome.call_id, "content": outcome.content})
                # 读完工具结果后模型容易切回英文思考，每轮补一条简短提醒。
                messages.append({"role": "system", "content": THINKING_LANGUAGE_HINT})
                await self._save_progress(state)
                continue
            answer = reply.content or "没有得到有效回答，请换个问法再试一次。"
            check = grounding.verify(answer, state.results, state.question)
            check.repaired = repaired
            state.verification = check.as_dict()
            can_repair = (not repaired and not exhausted and round_no < max_rounds
                          and time.monotonic() - started < settings.ai_agent_timeout_sec * 0.6)
            if check.status != "warned" or not can_repair:
                return answer
            # 数字对不上：带着原回答和不一致的数字再给模型一轮（可调用 calculate 修正）。
            repaired = True
            state.draft = ""
            # 修正提示是新一轮用户消息，只回传回答正文（上一轮思考内容不必、也不宜再回传）
            messages.append({"role": "assistant", "content": answer})
            messages.append({"role": "user", "content": THINKING_LANGUAGE_HINT
                             + grounding.repair_instruction(check.unmatched)})
        return "没有得到有效回答，请换个问法再试一次。"

    def _record_reply(self, state: RunState, round_no: int, reply: LlmReply) -> None:
        state.rounds = round_no
        state.model = reply.model
        state.prompt_tokens += reply.usage.get("promptTokens", 0)
        state.completion_tokens += reply.usage.get("completionTokens", 0)
        if reply.reasoning_content:
            self._set_thinking(state, round_no, reply.reasoning_content)
        # 带工具调用的轮次不算回答，清掉流式过程中写入的草稿
        state.draft = "" if reply.tool_calls else (reply.content or "")

    @staticmethod
    def _set_thinking(state: RunState, round_no: int, text: str) -> None:
        text = text.strip()
        entry = {"round": round_no,
                 "content": text[:THINKING_CHARS] + ("…（已截断）" if len(text) > THINKING_CHARS else "")}
        if state.thinking and state.thinking[-1]["round"] == round_no:
            state.thinking[-1] = entry
        else:
            state.thinking.append(entry)

    def _stream_callback(self, state: RunState, round_no: int):
        async def on_delta(reasoning: str, content: str) -> None:
            if reasoning:
                self._set_thinking(state, round_no, reasoning)
            if content:
                state.draft = content
            now = time.monotonic()
            if now - state.last_stream_save >= STREAM_SAVE_INTERVAL:
                state.last_stream_save = now
                await run_in_threadpool(self.repo.update_run, state.run_id,
                                        thinking_json=state.thinking, answer=state.draft or None)
        return on_delta

    @staticmethod
    def _compact(state: RunState, messages: list[dict[str, Any]]) -> None:
        """上下文超长时，从最早的工具结果开始替换为汇总，直到长度回到上限以内（最近一轮保持完整）。"""
        limit = max(1, settings.ai_agent_context_chars)
        size = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
        if size <= limit:
            return
        last_assistant = max((i for i, m in enumerate(messages) if m.get("role") == "assistant"), default=-1)
        for index, message in enumerate(messages):
            if size <= limit or index > last_assistant:
                break
            call_id = message.get("tool_call_id")
            if message.get("role") != "tool" or call_id in state.compacted or call_id not in state.tool_messages:
                continue
            result_id, result = state.tool_messages[call_id]
            compact = result.compact_for_model(result_id)
            size -= len(message["content"]) - len(compact)
            message["content"] = compact
            state.compacted.add(call_id)

    async def _execute(self, state: RunState, context: AgentContext, calls: list[dict[str, Any]],
                       round_no: int) -> list[CallOutcome]:
        outcomes: dict[int, CallOutcome] = {}
        business: list[tuple[int, dict[str, Any]]] = []
        computations: list[tuple[int, dict[str, Any]]] = []
        for index, call in enumerate(calls):
            function = call.get("function") or {}
            name = function.get("name") or ""
            call_id = call.get("id") or f"call_{index}"
            if index >= MAX_CALLS_PER_ROUND:
                outcomes[index] = CallOutcome(call_id, name, _error("本轮调用过多，请分批查询"), "invalid")
            elif name in META_TOOL_NAMES:
                outcomes[index] = await self._meta(state, context, call_id, name, function.get("arguments"))
            elif state.tool_calls + len(business) + len(computations) >= settings.ai_agent_max_tool_calls:
                outcomes[index] = CallOutcome(call_id, name, _error("已达到本次任务的查询次数上限"), "invalid")
            elif name == CALCULATE_TOOL:
                computations.append((index, call))
            else:
                business.append((index, call))
        results = await asyncio.gather(*(
            self._business(context, call.get("id") or f"call_{index}", call.get("function") or {})
            for index, call in business
        ))
        for (index, _call), outcome in zip(business, results):
            self._register(state, outcome)
            outcomes[index] = outcome
        # 计算放在查询之后，可以引用同一轮刚查到的结果。
        for index, call in computations:
            outcome = self._calculate(state, call.get("id") or f"call_{index}", call.get("function") or {})
            self._register(state, outcome)
            outcomes[index] = outcome
        ordered = [outcomes[index] for index in sorted(outcomes)]
        for outcome in ordered:
            if outcome.name in META_TOOL_NAMES:
                continue
            state.tool_calls += 1
            state.seq += 1
            await run_in_threadpool(
                self.repo.insert_step, state.run_id, state.seq, round_no, outcome.name, outcome.arguments,
                outcome.status, outcome.row_count, outcome.duration_ms, outcome.error)
        return ordered

    @staticmethod
    def _register(state: RunState, outcome: CallOutcome) -> None:
        """给成功的结果编号，写入运行记录，并生成带编号的模型输入。"""
        if outcome.result is None:
            return
        result_id = len(state.results) + 1
        state.results.append({"tool": outcome.name, **outcome.result.for_storage(result_id)})
        state.tool_messages[outcome.call_id] = (result_id, outcome.result)
        outcome.content = outcome.result.for_model(result_id)

    async def _business(self, context: AgentContext, call_id: str, function: dict[str, Any]) -> CallOutcome:
        name = function.get("name") or ""
        tool = self.tools.get(name)
        if tool is None:
            return CallOutcome(call_id, name, _error(f"不存在工具 {name}"), "invalid", error="未知工具")
        started = time.monotonic()
        arguments = None
        try:
            args = tool.parse(function.get("arguments"))
            arguments = args.model_dump()
            if tool.permission:
                context.require(tool.permission)
            if tool.data_scope_all and context.access.scope(tool.data_scope_all) is not None:
                raise ToolPermissionError("该数据按店铺返回、无法按负责人拆分，只对「全部数据」范围的账号开放")
            async with self._semaphore:
                result = await asyncio.wait_for(
                    run_in_threadpool(tool.handler, context, args),
                    timeout=tool.timeout_sec or settings.ai_agent_tool_timeout_sec)
        except ToolArgumentError as exc:
            return self._outcome(call_id, name, "invalid", started, arguments, str(exc))
        except ToolPermissionError as exc:
            return self._outcome(call_id, name, "denied", started, arguments, str(exc))
        except asyncio.TimeoutError:
            return self._outcome(call_id, name, "failed", started, arguments, "查询超时，请缩小范围后重试")
        except ValueError as exc:  # 服务层的业务校验（如月份不存在），信息可直接展示。
            return self._outcome(call_id, name, "failed", started, arguments, str(exc))
        except Exception:
            LOG.exception("agent tool failed tool=%s request_id=%s", name, context.request_id)
            return self._outcome(call_id, name, "failed", started, arguments, "查询失败（服务端错误），请稍后重试")
        return CallOutcome(call_id, name, "", "completed", arguments, len(result.rows),
                           int((time.monotonic() - started) * 1000), None, result)

    def _calculate(self, state: RunState, call_id: str, function: dict[str, Any]) -> CallOutcome:
        started = time.monotonic()
        arguments = None
        try:
            args = _CALCULATE_PARSER.parse(function.get("arguments"))
            arguments = args.model_dump()
            result = calculate(state.results, args)
        except (ToolArgumentError, CalculationError) as exc:
            return self._outcome(call_id, CALCULATE_TOOL, "invalid", started, arguments, str(exc))
        return CallOutcome(call_id, CALCULATE_TOOL, "", "completed", arguments, len(result.rows),
                           int((time.monotonic() - started) * 1000), None, result)

    @staticmethod
    def _outcome(call_id, name, status, started, arguments, message) -> CallOutcome:
        return CallOutcome(call_id, name, _error(message), status, arguments,
                           duration_ms=int((time.monotonic() - started) * 1000), error=message)

    async def _meta(self, state: RunState, context: AgentContext, call_id: str, name: str,
                    raw_arguments: Any) -> CallOutcome:
        try:
            data = json.loads(raw_arguments or "{}") if not isinstance(raw_arguments, dict) else raw_arguments
            args = META_ARGS[name].model_validate(data)
        except Exception as exc:
            return CallOutcome(call_id, name, _error(f"参数不合法：{exc}"), "invalid")
        if name == PLAN_TOOL:
            state.plan = [step.model_dump() for step in args.steps]
            await self._save_progress(state)
            return CallOutcome(call_id, name, json.dumps({"ok": True}), "completed")
        try:
            if name == SAVE_MEMORY_TOOL:
                # 用户明确要求记住的直接生效；模型推断出的偏好先挂起，等用户在页面确认。
                status = "active" if args.explicit else "pending"
                memory_id = await run_in_threadpool(
                    self.repo.save_memory, context.user_id, args.category, args.content.strip(), state.run_id,
                    status)
                return CallOutcome(call_id, name, json.dumps(
                    {"ok": True, "memory_id": memory_id, "status": status,
                     "note": "已记住" if status == "active" else "已提交给用户确认，确认后生效"},
                    ensure_ascii=False), "completed")
            if name == FORGET_MEMORY_TOOL:
                deleted = await run_in_threadpool(self.repo.delete_memory, context.user_id, args.memory_id)
                return CallOutcome(call_id, name, json.dumps({"ok": deleted}), "completed")
        except ValueError as exc:
            return CallOutcome(call_id, name, _error(str(exc)), "failed")
        return CallOutcome(call_id, name, _error("未知元工具"), "invalid")

    # ------------------------------------------------------------ 持久化

    async def _save_progress(self, state: RunState) -> None:
        await run_in_threadpool(
            self.repo.update_run, state.run_id, plan_json=state.plan, results_json=state.results,
            thinking_json=state.thinking, answer=state.draft or None, rounds=state.rounds,
            tool_calls=state.tool_calls, prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens, model=state.model)

    async def _complete(self, state: RunState, context: AgentContext, conversation_uuid: str,
                        answer: str) -> dict[str, Any]:
        plan = [{**step, "status": "completed" if step["status"] == "in_progress" else step["status"]}
                for step in state.plan]
        state.plan = plan
        # 会话记录里的回答把 [[表:N]] 展开成 Markdown 表格：重新打开会话、作为后续上下文时都能看到数据。
        await run_in_threadpool(
            self.conversations.append_message, context.user_id, context.username, conversation_uuid,
            "assistant", expand_table_refs(answer, state.results), request_id=context.request_id,
            model=state.model, prompt_tokens=state.prompt_tokens, completion_tokens=state.completion_tokens,
            total_tokens=state.prompt_tokens + state.completion_tokens)
        await run_in_threadpool(
            self.repo.update_run, state.run_id, status="completed", answer=answer, plan_json=plan,
            results_json=state.results, thinking_json=state.thinking, verification_json=state.verification,
            rounds=state.rounds, tool_calls=state.tool_calls, prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens, model=state.model, completed_at=datetime.now())
        return {"status": "completed", "answer": answer, "verification": state.verification}

    async def _refresh_summary(self, context: AgentContext, conversation_uuid: str) -> None:
        try:
            await refresh_summary(self.llm, self.conversations, context.user_id, conversation_uuid,
                                  keep_recent=HISTORY_MESSAGES, request_id=context.request_id)
        except Exception:  # 摘要失败不影响本次回答，下次再试。
            LOG.warning("conversation summary failed conversation=%s", conversation_uuid, exc_info=True)

    async def _fail(self, state: RunState, context: AgentContext, conversation_uuid: str,
                    message: str) -> dict[str, Any]:
        try:
            await run_in_threadpool(
                self.conversations.append_message, context.user_id, context.username, conversation_uuid,
                "assistant", message, request_id=context.request_id, is_error=True, model=state.model)
        except Exception:
            LOG.exception("persist agent error message failed run_id=%s", state.run_id)
        await run_in_threadpool(
            self.repo.update_run, state.run_id, status="failed", error_message=message[:1000],
            answer=None, plan_json=state.plan, results_json=state.results, thinking_json=state.thinking,
            rounds=state.rounds, tool_calls=state.tool_calls, completed_at=datetime.now())
        return {"status": "failed", "error": message}


def _error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def expand_table_refs(answer: str, results: list[dict[str, Any]]) -> str:
    """把 [[表:N]] 换成 Markdown 表格（最多 EXPANDED_TABLE_ROWS 行）；编号不存在的引用直接去掉。"""
    def replace(match: re.Match) -> str:
        index = int(match.group(1))
        if not 1 <= index <= len(results):
            return ""
        result = results[index - 1]
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        if not columns:
            return ""
        lines = ["| " + " | ".join(c["label"] for c in columns) + " |",
                 "| " + " | ".join("---" for _ in columns) + " |"]
        lines += ["| " + " | ".join(_cell(row.get(c["key"])) for c in columns) + " |"
                  for row in rows[:EXPANDED_TABLE_ROWS]]
        total = result.get("rowCount") or len(rows)
        if total > EXPANDED_TABLE_ROWS:
            lines.append(f"\n（共{total}行，此处显示前{EXPANDED_TABLE_ROWS}行）")
        return "\n" + "\n".join(lines) + "\n"

    return TABLE_REF.sub(replace, answer or "")


# ---------------------------------------------------------------- 后台启动

_TASKS: set[asyncio.Task] = set()


async def start_run(context: AgentContext, conversation_uuid: str, question: str,
                    page: dict[str, str] | None = None, runner: AgentRunner | None = None,
                    source: str = "chat") -> str:
    """登记运行并在当前事件循环后台执行，立即返回 run_id 供前端轮询。"""
    run_id = str(uuid.uuid4())
    await run_in_threadpool(runs_repo.create_run, run_id, conversation_uuid, context.user_id,
                            context.username, question, context.request_id, source)
    # 定时简报的会话标题固定为「定时简报：…」，不被首条提问覆盖
    task = asyncio.create_task((runner or AgentRunner()).run(
        run_id, context, conversation_uuid, question, page, keep_title=source == "brief"))
    _TASKS.add(task)  # 保留引用，避免任务被垃圾回收中途取消。
    task.add_done_callback(_TASKS.discard)
    return run_id
