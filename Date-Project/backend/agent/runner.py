"""数据助手的任务编排：规划 → 并行调用工具 → 观察结果 → 继续或作答。

每轮把模型发起的工具调用分两类执行：元工具（计划、记忆）按顺序处理，业务查询并行执行
（受并发上限和单次超时约束）。轮次、调用次数、总时长三类预算任一用尽，就不再提供工具、
要求模型基于已有结果作答。每一步的进度都写入 ai_agent_run，前端轮询展示。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from starlette.concurrency import run_in_threadpool

from backend.agent.context import AgentContext, ToolPermissionError
from backend.agent.llm import AgentChatClient, LlmError
from backend.agent.prompts import THINKING_LANGUAGE_HINT, build_system_prompt
from backend.agent.tools.base import Tool, ToolArgumentError, ToolResult
from backend.agent.tools.business import BUSINESS_TOOLS
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
FINAL_INSTRUCTION = "执行预算已用完或已获得足够数据。请不要再调用工具，直接基于上面的工具结果回答用户；未查到的部分如实说明。"


@dataclass
class RunState:
    run_id: str
    plan: list[dict[str, str]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    thinking: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    seq: int = 0


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


class AgentRunner:
    def __init__(self, llm: AgentChatClient | None = None, tools: list[Tool] | None = None,
                 repo=runs_repo, conversations=ai_conversation_repository):
        self.llm = llm or AgentChatClient()
        self.tools = {tool.name: tool for tool in (tools if tools is not None else BUSINESS_TOOLS)}
        self.repo = repo
        self.conversations = conversations
        self._semaphore = asyncio.Semaphore(max(1, settings.ai_agent_parallel_tools))

    # ------------------------------------------------------------ 入口

    async def run(self, run_id: str, context: AgentContext, conversation_uuid: str,
                  question: str, page: dict[str, str] | None = None) -> dict[str, Any]:
        state = RunState(run_id)
        started = time.monotonic()
        try:
            memories = await run_in_threadpool(self.repo.list_memories, context.user_id)
            history = await run_in_threadpool(
                self.conversations.context_messages, context.user_id, conversation_uuid, HISTORY_MESSAGES)
            await run_in_threadpool(
                self.conversations.append_message, context.user_id, context.username, conversation_uuid,
                "user", question, request_id=context.request_id,
                first_message_title=" ".join(question.split())[:40])
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": build_system_prompt(context, memories, history, page)},
                # 会话记录保存用户原话；发给模型的提问前固定加上思考语言要求。
                {"role": "user", "content": f"{THINKING_LANGUAGE_HINT}{question}"},
            ]
            available = [tool for tool in self.tools.values() if tool.available_to(context)]
            schemas = meta_schemas() + [tool.schema() for tool in available]
            answer = await self._loop(state, context, messages, schemas, started)
        except LlmError as exc:
            return await self._fail(state, context, conversation_uuid, str(exc))
        except Exception:  # 未预期错误：记录详情，对用户只给通用提示。
            LOG.exception("agent run failed run_id=%s", run_id)
            return await self._fail(state, context, conversation_uuid, "数据助手执行失败，请稍后重试")
        return await self._complete(state, context, conversation_uuid, answer)

    # ------------------------------------------------------------ 主循环

    async def _loop(self, state: RunState, context: AgentContext, messages: list[dict[str, Any]],
                    schemas: list[dict[str, Any]], started: float) -> str:
        max_rounds = max(1, settings.ai_agent_max_rounds)
        for round_no in range(1, max_rounds + 1):
            elapsed = time.monotonic() - started
            exhausted = (
                round_no == max_rounds
                or state.tool_calls >= settings.ai_agent_max_tool_calls
                or elapsed >= settings.ai_agent_timeout_sec * 0.75
            )
            if exhausted:
                messages.append({"role": "system", "content": FINAL_INSTRUCTION})
            reply = await self.llm.complete(
                messages, None if exhausted else schemas, request_id=context.request_id)
            state.rounds = round_no
            state.model = reply.model
            state.prompt_tokens += reply.usage.get("promptTokens", 0)
            state.completion_tokens += reply.usage.get("completionTokens", 0)
            if reply.reasoning_content:
                text = reply.reasoning_content.strip()
                state.thinking.append({
                    "round": round_no,
                    "content": text[:THINKING_CHARS] + ("…（已截断）" if len(text) > THINKING_CHARS else ""),
                })
                await self._save_progress(state)
            if exhausted or not reply.tool_calls:
                return reply.content or "没有得到有效回答，请换个问法再试一次。"
            messages.append(reply.as_message())
            outcomes = await self._execute(state, context, reply.tool_calls, round_no)
            for outcome in outcomes:
                messages.append({"role": "tool", "tool_call_id": outcome.call_id, "content": outcome.content})
            # 读完工具结果后模型容易切回英文思考，每轮补一条简短提醒。
            messages.append({"role": "system", "content": THINKING_LANGUAGE_HINT})
            await self._save_progress(state)
        return "没有得到有效回答，请换个问法再试一次。"

    async def _execute(self, state: RunState, context: AgentContext, calls: list[dict[str, Any]],
                       round_no: int) -> list[CallOutcome]:
        outcomes: dict[int, CallOutcome] = {}
        business: list[tuple[int, dict[str, Any]]] = []
        for index, call in enumerate(calls):
            function = call.get("function") or {}
            name = function.get("name") or ""
            call_id = call.get("id") or f"call_{index}"
            if index >= MAX_CALLS_PER_ROUND:
                outcomes[index] = CallOutcome(call_id, name, _error("本轮调用过多，请分批查询"), "invalid")
            elif name in META_TOOL_NAMES:
                outcomes[index] = await self._meta(state, context, call_id, name, function.get("arguments"))
            elif state.tool_calls + len(business) >= settings.ai_agent_max_tool_calls:
                outcomes[index] = CallOutcome(call_id, name, _error("已达到本次任务的查询次数上限"), "invalid")
            else:
                business.append((index, call))
        results = await asyncio.gather(*(
            self._business(context, call.get("id") or f"call_{index}", call.get("function") or {})
            for index, call in business
        ))
        for (index, _call), outcome in zip(business, results):
            outcomes[index] = outcome
        ordered = [outcomes[index] for index in sorted(outcomes)]
        for outcome in ordered:
            if outcome.name in META_TOOL_NAMES:
                continue
            state.tool_calls += 1
            state.seq += 1
            if outcome.result is not None:
                state.results.append({"tool": outcome.name, **outcome.result.for_storage()})
            await run_in_threadpool(
                self.repo.insert_step, state.run_id, state.seq, round_no, outcome.name, outcome.arguments,
                outcome.status, outcome.row_count, outcome.duration_ms, outcome.error)
        return ordered

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
            async with self._semaphore:
                result = await asyncio.wait_for(
                    run_in_threadpool(tool.handler, context, args), timeout=settings.ai_agent_tool_timeout_sec)
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
        return CallOutcome(call_id, name, result.for_model(), "completed", arguments, len(result.rows),
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
                memory_id = await run_in_threadpool(
                    self.repo.save_memory, context.user_id, args.category, args.content.strip(), state.run_id)
                return CallOutcome(call_id, name, json.dumps({"ok": True, "memory_id": memory_id}), "completed")
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
            thinking_json=state.thinking, rounds=state.rounds, tool_calls=state.tool_calls,
            prompt_tokens=state.prompt_tokens, completion_tokens=state.completion_tokens, model=state.model)

    async def _complete(self, state: RunState, context: AgentContext, conversation_uuid: str,
                        answer: str) -> dict[str, Any]:
        plan = [{**step, "status": "completed" if step["status"] == "in_progress" else step["status"]}
                for step in state.plan]
        state.plan = plan
        await run_in_threadpool(
            self.conversations.append_message, context.user_id, context.username, conversation_uuid,
            "assistant", answer, request_id=context.request_id, model=state.model,
            prompt_tokens=state.prompt_tokens, completion_tokens=state.completion_tokens,
            total_tokens=state.prompt_tokens + state.completion_tokens)
        await run_in_threadpool(
            self.repo.update_run, state.run_id, status="completed", answer=answer, plan_json=plan,
            results_json=state.results, thinking_json=state.thinking, rounds=state.rounds,
            tool_calls=state.tool_calls, prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens, model=state.model, completed_at=datetime.now())
        return {"status": "completed", "answer": answer}

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
            plan_json=state.plan, results_json=state.results, thinking_json=state.thinking,
            rounds=state.rounds, tool_calls=state.tool_calls, completed_at=datetime.now())
        return {"status": "failed", "error": message}


def _error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


# ---------------------------------------------------------------- 后台启动

_TASKS: set[asyncio.Task] = set()


async def start_run(context: AgentContext, conversation_uuid: str, question: str,
                    page: dict[str, str] | None = None, runner: AgentRunner | None = None) -> str:
    """登记运行并在当前事件循环后台执行，立即返回 run_id 供前端轮询。"""
    run_id = str(uuid.uuid4())
    await run_in_threadpool(runs_repo.create_run, run_id, conversation_uuid, context.user_id,
                            context.username, question, context.request_id)
    task = asyncio.create_task((runner or AgentRunner()).run(run_id, context, conversation_uuid, question, page))
    _TASKS.add(task)  # 保留引用，避免任务被垃圾回收中途取消。
    task.add_done_callback(_TASKS.discard)
    return run_id
