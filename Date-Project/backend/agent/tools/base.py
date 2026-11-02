from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from backend.agent.context import AgentContext

# 交给模型的明细行数上限；完整结果保存在运行记录里给页面表格使用。
MODEL_ROW_LIMIT = 30
STORED_ROW_LIMIT = 500


@dataclass
class ToolResult:
    """一次工具调用的结果。

    summary 是给模型看的汇总口径；rows/columns 是明细表格，source/period 用于在回答里
    注明数据来源与统计区间，notes 记录口径说明或不完整提示。
    """

    title: str
    summary: dict[str, Any] = field(default_factory=dict)
    columns: list[tuple[str, str]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""
    period: str = ""
    notes: list[str] = field(default_factory=list)

    def for_model(self, result_id: int | None = None) -> str:
        payload = {
            "result_id": result_id,
            "title": self.title,
            "source": self.source,
            "period": self.period,
            "summary": self.summary,
            "notes": self.notes,
            "row_count": len(self.rows),
            "rows": [
                {label: row.get(key) for key, label in self.columns}
                for row in self.rows[:MODEL_ROW_LIMIT]
            ],
        }
        if len(self.rows) > MODEL_ROW_LIMIT:
            payload["rows_truncated"] = f"仅展示前{MODEL_ROW_LIMIT}行，完整{len(self.rows)}行已在页面表格中展示"
        if result_id is not None and self.rows:
            payload["table_ref"] = f"[[表:{result_id}]]"
        return json.dumps(payload, ensure_ascii=False, default=_json_default)

    def compact_for_model(self, result_id: int | None = None) -> str:
        """上下文过长时替换早期工具结果：保留汇总与口径，明细改为按编号引用。"""
        return json.dumps({
            "result_id": result_id, "title": self.title, "source": self.source, "period": self.period,
            "summary": self.summary, "notes": self.notes, "row_count": len(self.rows),
            "rows_omitted": "明细已从上下文省略：展示用 [[表:编号]]，计算用 calculate 工具引用 result_id",
        }, ensure_ascii=False, default=_json_default)

    def for_storage(self, result_id: int | None = None) -> dict[str, Any]:
        return {
            "id": result_id,
            "title": self.title,
            "source": self.source,
            "period": self.period,
            "summary": self.summary,
            "notes": self.notes,
            "columns": [{"key": key, "label": label} for key, label in self.columns],
            "rows": self.rows[:STORED_ROW_LIMIT],
            "rowCount": len(self.rows),
        }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def money(value: Any, digits: int = 2) -> float | None:
    if value in (None, ""):
        return None
    return round(float(Decimal(str(value))), digits)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[AgentContext, BaseModel], ToolResult]
    permission: str | None = None
    title: str = ""
    # 元工具（计划、记忆）在主线程顺序执行；业务查询工具可并行。
    parallel: bool = True
    # 只对该业务模块数据范围为「全部数据」的账号开放（数据无法按负责人拆分时使用，如 eBay 店铺级实时数据）
    data_scope_all: str | None = None
    # 单次调用超时（秒）；为空用 AI_AGENT_TOOL_TIMEOUT_SEC。实时调用外部接口的工具需要更长时间
    timeout_sec: int | None = None

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _clean_schema(self.args_model.model_json_schema()),
            },
        }

    def parse(self, raw_arguments: str | dict | None) -> BaseModel:
        if isinstance(raw_arguments, dict):
            data = raw_arguments
        else:
            try:
                data = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError as exc:
                raise ToolArgumentError(f"参数不是合法JSON：{exc.msg}") from exc
        if not isinstance(data, dict):
            raise ToolArgumentError("参数必须是JSON对象")
        try:
            return self.args_model.model_validate(data)
        except ValidationError as exc:
            problems = "；".join(
                f"{'.'.join(str(p) for p in err['loc']) or '参数'}：{err['msg']}" for err in exc.errors()[:5]
            )
            raise ToolArgumentError(problems) from exc

    def available_to(self, context: AgentContext) -> bool:
        if self.permission is not None and not context.access.has(self.permission):
            return False
        return self.data_scope_all is None or context.access.scope(self.data_scope_all) is None


class ToolArgumentError(ValueError):
    """模型给出的参数不合法；把原因返回给模型让它修正，而不是终止整个任务。"""


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """去掉 pydantic 生成的 title 等冗余字段，并内联 $defs，减少提示词体积。"""
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(dict(defs[node["$ref"].split("/")[-1]]))
            return {key: resolve(value) for key, value in node.items() if key != "title"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)
