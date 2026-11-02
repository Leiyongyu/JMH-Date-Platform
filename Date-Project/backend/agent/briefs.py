"""定时简报：用户保存一个固定问题和执行周期，到点由 RuoYi 定时任务带上该用户当前的权限触发执行。

时间一律按北京时间（无时区的本地时间）保存和比较。简报结果写进专属会话「定时简报：标题」，
用户在助手的会话列表里查看；每次执行都是一次普通的 agent 运行（source=brief），同样有核对、反馈。
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from backend.agent.context import AgentContext
from backend.repositories import ai_agent_repository as runs_repo
from backend.repositories.ai_conversation_repository import ConversationNotFoundError, ai_conversation_repository

BEIJING = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING).replace(tzinfo=None, microsecond=0)


class BriefRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=60)
    question: str = Field(..., min_length=2, max_length=1000)
    frequency: Literal["daily", "weekly", "monthly"]
    weekday: int | None = Field(None, ge=1, le=7, description="每周几执行，1=周一")
    month_day: int | None = Field(None, ge=1, le=28, description="每月几号执行（最大 28，避免小月缺日）")
    run_hour: int = Field(9, ge=0, le=23)
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self) -> "BriefRequest":
        if self.frequency == "weekly" and self.weekday is None:
            raise ValueError("每周执行需要选择星期几")
        if self.frequency == "monthly" and self.month_day is None:
            raise ValueError("每月执行需要选择日期")
        return self


def next_run(frequency: str, weekday: int | None, month_day: int | None, run_hour: int,
             after: datetime) -> datetime:
    """after 之后（不含）的下一个执行时刻。"""
    base = after.replace(minute=0, second=0, microsecond=0)
    if frequency == "daily":
        candidate = base.replace(hour=run_hour)
        return candidate if candidate > after else candidate + timedelta(days=1)
    if frequency == "weekly":
        candidate = base.replace(hour=run_hour) + timedelta(days=(int(weekday or 1) - 1 - base.weekday()) % 7)
        return candidate if candidate > after else candidate + timedelta(days=7)
    day = int(month_day or 1)
    candidate = base.replace(day=min(day, calendar.monthrange(base.year, base.month)[1]), hour=run_hour)
    if candidate > after:
        return candidate
    year, month = (base.year + 1, 1) if base.month == 12 else (base.year, base.month + 1)
    return candidate.replace(year=year, month=month, day=min(day, calendar.monthrange(year, month)[1]))


def save(user_id: int, username: str, brief_id: int | None, payload: BriefRequest) -> dict:
    fields = payload.model_dump()
    upcoming = next_run(payload.frequency, payload.weekday, payload.month_day, payload.run_hour, beijing_now()) \
        if payload.enabled else None
    saved_id = runs_repo.save_brief(user_id, username, brief_id, fields, upcoming)
    return runs_repo.get_brief(user_id, saved_id)


async def run_brief(context: AgentContext, brief_id: int, *, force: bool) -> dict:
    """执行一次简报。定时触发（force=False）时先抢占本周期，抢不到说明已执行过，直接跳过。"""
    from backend.agent.runner import start_run

    brief = await run_in_threadpool(runs_repo.get_brief, context.user_id, brief_id)
    if brief is None:
        raise LookupError("定时简报不存在或无权访问")
    now = beijing_now()
    upcoming = next_run(brief["frequency"], brief["weekday"], brief["monthDay"], brief["runHour"], now)
    claimed = await run_in_threadpool(runs_repo.claim_brief, context.user_id, brief_id, now, upcoming, force)
    if not claimed:
        return {"briefId": brief_id, "skipped": True}
    conversation_id = await run_in_threadpool(_ensure_conversation, context, brief)
    run_id = await start_run(context, conversation_id, brief["question"], {"title": f"定时简报：{brief['title']}"},
                             source="brief")
    await run_in_threadpool(runs_repo.set_brief_run, brief_id, conversation_id, run_id)
    return {"briefId": brief_id, "runId": run_id, "conversationId": conversation_id, "skipped": False}


def _ensure_conversation(context: AgentContext, brief: dict) -> str:
    """沿用简报的专属会话；用户删掉了就新建一个。"""
    if brief.get("conversationId"):
        try:
            ai_conversation_repository.get_summary(context.user_id, brief["conversationId"])
            return brief["conversationId"]
        except ConversationNotFoundError:
            pass
    created = ai_conversation_repository.create(context.user_id, context.username, f"定时简报：{brief['title']}"[:200])
    return created["id"]
