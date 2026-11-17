"""会话滚动摘要：最近 keep_recent 条消息原样带给模型，更早的内容压缩成一段摘要。

只有「未被摘要覆盖、又已滑出最近窗口」的消息累计到 SUMMARY_BATCH 条才调用一次模型，
避免每轮都多花一次请求。摘要不带思考模式，结果保存在 ai_conversations.summary。
"""
from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool

SUMMARY_BATCH = 8
SUMMARY_CHARS = 800
MESSAGE_CHARS = 600

SUMMARY_PROMPT = """你负责压缩一段数据助手对话的历史，供后续回答理解上下文。
请用简体中文输出不超过 400 字的摘要：保留用户关心的月份、店铺、组别、负责人、SKU 等对象，已得出的关键结论和数字，
以及用户提出的口径要求；去掉寒暄和重复内容。只输出摘要正文。"""


async def refresh_summary(llm, conversations, user_id: int, conversation_uuid: str, *,
                          keep_recent: int, request_id: str = "") -> bool:
    state = await run_in_threadpool(conversations.summary_state, user_id, conversation_uuid)
    if not state:
        return False
    covered = int(state.get("summaryMessageCount") or 0)
    pending_until = int(state.get("messageCount") or 0) - keep_recent
    if pending_until - covered < SUMMARY_BATCH:
        return False
    messages: list[dict[str, Any]] = await run_in_threadpool(
        conversations.messages_range, user_id, conversation_uuid, covered, pending_until - covered)
    if not messages:
        return False
    lines = []
    for message in messages:
        role = "用户" if message.get("role") == "user" else "助手"
        content = " ".join(str(message.get("content") or "").split())
        lines.append(f"{role}：{content[:MESSAGE_CHARS]}")
    previous = (state.get("summary") or "").strip()
    user_text = (f"已有摘要：\n{previous}\n\n" if previous else "") + "需要并入摘要的新对话：\n" + "\n".join(lines)
    reply = await llm.complete(
        [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": user_text}],
        request_id=request_id, thinking=False)
    text = (reply.content or "").strip()
    if not text:
        return False
    await run_in_threadpool(conversations.save_summary, user_id, conversation_uuid,
                            text[:SUMMARY_CHARS], pending_until)
    return True
