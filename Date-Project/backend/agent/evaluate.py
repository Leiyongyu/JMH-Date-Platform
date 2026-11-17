"""数据助手评测：用标准问题跑完整流程（真实模型 + 真实只读数据），检查工具选择、数字核对和回答要点。

运行记录、会话都写在内存里，不写数据库；业务查询按传入的权限执行（默认管理员）。

    python -m backend.agent.evaluate                       # 跑 agent_eval/cases.json 全部用例
    python -m backend.agent.evaluate --case sales_mom      # 只跑指定用例
    python -m backend.agent.evaluate --export-feedback     # 导出被点踩的提问，人工整理后补进评测集
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.agent.context import AgentAccess, AgentContext
from backend.config import PROJECT_ROOT

CASES_FILE = PROJECT_ROOT / "agent_eval" / "cases.json"
REPORT_DIR = PROJECT_ROOT / "agent_eval" / "reports"


class MemoryRepo:
    """运行记录只留在内存里。"""

    def __init__(self):
        self.run: dict[str, Any] = {}
        self.steps: list[dict[str, Any]] = []

    def list_memories(self, user_id):
        return []

    def update_run(self, run_id, **fields):
        self.run.update(fields)

    def insert_step(self, run_id, seq, round_no, tool, arguments, status, rows, duration, error):
        self.steps.append({"tool": tool, "status": status, "rows": rows, "error": error})

    def save_memory(self, user_id, category, content, run_id, status="active"):
        return 0

    def delete_memory(self, user_id, memory_id):
        return False


class MemoryConversations:
    def __init__(self):
        self.messages: list[tuple[str, str]] = []

    def context_messages(self, user_id, conversation_uuid, limit):
        return []

    def context_summary(self, user_id, conversation_uuid):
        return None

    def summary_state(self, user_id, conversation_uuid):
        return None

    def append_message(self, user_id, username, conversation_uuid, role, content, **kwargs):
        self.messages.append((role, content))
        return len(self.messages)


@dataclass
class CaseResult:
    id: str
    question: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    verification: dict[str, Any] | None = None
    seconds: float = 0.0
    tokens: int = 0
    answer: str = ""


def check(case: dict[str, Any], status: str, tools: list[str], answer: str,
          verification: dict[str, Any] | None) -> list[str]:
    problems = []
    if status != "completed":
        problems.append(f"运行失败：{status}")
    used = set(tools)
    if case.get("expect_tools") and not used & set(case["expect_tools"]):
        problems.append(f"未调用 {'/'.join(case['expect_tools'])}")
    for name in case.get("expect_all_tools") or []:
        if name not in used:
            problems.append(f"未调用 {name}")
    if case.get("expect_any_tools") and not used & set(case["expect_any_tools"]):
        problems.append(f"未调用 {'/'.join(case['expect_any_tools'])} 中任何一个")
    for name in case.get("forbid_tools") or []:
        if name in used:
            problems.append(f"不应调用 {name}")
    groups = case.get("answer_contains") or []
    if groups and not any(all(word in answer for word in group) for group in groups):
        problems.append("回答缺少要点：" + " 或 ".join("+".join(g) for g in groups))
    if verification and verification.get("status") == "warned":
        problems.append("数字核对未通过：" + "、".join(verification.get("unmatched") or []))
    return problems


async def run_case(case: dict[str, Any], access: AgentAccess) -> CaseResult:
    from backend.agent.runner import AgentRunner

    repo, conversations = MemoryRepo(), MemoryConversations()
    context = AgentContext(user_id=0, username="评测", access=access, request_id=f"eval-{case['id']}",
                           sources=frozenset(case.get("sources") or []))
    started = time.monotonic()
    outcome = await AgentRunner(repo=repo, conversations=conversations).run(
        f"eval-{case['id']}", context, "eval", case["question"], None)
    tools = [step["tool"] for step in repo.steps if step["status"] == "completed"]
    answer = outcome.get("answer") or outcome.get("error") or ""
    problems = check(case, outcome["status"], tools, answer, outcome.get("verification"))
    return CaseResult(
        id=case["id"], question=case["question"], passed=not problems, problems=problems, tools=tools,
        verification=outcome.get("verification"), seconds=round(time.monotonic() - started, 1),
        tokens=int(repo.run.get("prompt_tokens") or 0) + int(repo.run.get("completion_tokens") or 0),
        answer=answer,
    )


def load_cases(path: Path, only: list[str] | None) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    return [case for case in cases if not only or case["id"] in only]


def export_feedback(path: Path) -> int:
    from backend.repositories import ai_agent_repository

    rows = ai_agent_repository.down_voted_runs()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="数据助手评测")
    parser.add_argument("--cases", type=Path, default=CASES_FILE)
    parser.add_argument("--case", action="append", help="只跑指定用例 id，可重复")
    parser.add_argument("--permissions", default="*:*:*", help="逗号分隔的权限，默认管理员")
    parser.add_argument("--export-feedback", action="store_true", help="导出被点踩的提问到 agent_eval/feedback.json")
    args = parser.parse_args(argv)
    if args.export_feedback:
        target = PROJECT_ROOT / "agent_eval" / "feedback.json"
        print(f"已导出 {export_feedback(target)} 条点踩记录：{target}")
        return 0
    access = AgentAccess.from_payload({"permissions": args.permissions.split(","), "scopes": {}})
    results = []
    for case in load_cases(args.cases, args.case):
        result = asyncio.run(run_case(case, access))
        results.append(result)
        mark = "通过" if result.passed else "失败"
        print(f"[{mark}] {result.id} {result.seconds}s {result.tokens}tok 工具={','.join(result.tools) or '-'}"
              + ("" if result.passed else "  " + "；".join(result.problems)))
    passed = sum(r.passed for r in results)
    print(f"\n合计 {passed}/{len(results)} 通过")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    report.write_text(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"明细：{report}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
