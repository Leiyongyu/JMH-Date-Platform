"""助手自身的元工具：维护执行计划、读写用户长期记忆。由 runner 直接处理，不访问业务数据。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.agent.tools.base import _clean_schema

PLAN_TOOL = "update_plan"
SAVE_MEMORY_TOOL = "save_memory"
FORGET_MEMORY_TOOL = "forget_memory"
META_TOOL_NAMES = {PLAN_TOOL, SAVE_MEMORY_TOOL, FORGET_MEMORY_TOOL}


class PlanStep(BaseModel):
    title: str = Field(..., min_length=1, max_length=60, description="步骤，如「查询10月综合绩效排名」")
    status: Literal["pending", "in_progress", "completed", "skipped"] = "pending"


class UpdatePlanArgs(BaseModel):
    steps: list[PlanStep] = Field(..., min_length=1, max_length=8, description="完整步骤清单（每次传全部步骤）")


class SaveMemoryArgs(BaseModel):
    content: str = Field(..., min_length=2, max_length=200,
                         description="要长期记住的内容，用第三人称简述，如「用户默认看德国站」")
    category: Literal["preference", "fact", "instruction"] = Field(
        "preference", description="preference=偏好，fact=业务事实，instruction=工作习惯")
    explicit: bool = Field(False, description="用户本轮明确要求记住（说了「记住」「以后」「默认」）时为 true；"
                                              "根据对话推断的偏好填 false，会先请用户确认再生效")


class ForgetMemoryArgs(BaseModel):
    memory_id: int = Field(..., ge=1, description="要删除的记忆编号")


META_ARGS = {
    PLAN_TOOL: UpdatePlanArgs,
    SAVE_MEMORY_TOOL: SaveMemoryArgs,
    FORGET_MEMORY_TOOL: ForgetMemoryArgs,
}

META_DESCRIPTIONS = {
    PLAN_TOOL: "制定或更新本次任务的执行计划。需要查数据时先调用一次列出步骤，每完成一步再更新状态。",
    SAVE_MEMORY_TOOL: "保存长期偏好或业务事实（如「以后默认看人民币」），下次对话自动带上。用户明确要求时 explicit=true 直接生效；"
                      "从对话中推断出的偏好 explicit=false，由用户确认后生效。不要保存账号、密码、权限。",
    FORGET_MEMORY_TOOL: "删除一条长期记忆（用户说「忘掉」「不用记」时调用）。",
}


def meta_schemas() -> list[dict]:
    return [
        {"type": "function", "function": {
            "name": name, "description": META_DESCRIPTIONS[name],
            "parameters": _clean_schema(model.model_json_schema()),
        }}
        for name, model in META_ARGS.items()
    ]
