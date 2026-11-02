from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import HTTPException

from backend.config import settings

LOG = logging.getLogger(__name__)


class LlmError(RuntimeError):
    """模型调用失败，message 可直接展示给用户。"""


@dataclass
class LlmReply:
    content: str
    reasoning_content: str | None
    tool_calls: list[dict[str, Any]]
    model: str
    finish_reason: str | None
    usage: dict[str, int] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        """回填到下一次请求的 assistant 消息。

        DeepSeek 思考模式下带 tools 的请求必须原样回传 reasoning_content，否则返回 400。
        """
        message: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.reasoning_content:
            message["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            message["tool_calls"] = self.tool_calls
        return message


class DeepSeekChatClient:
    def __init__(self, *, thinking: bool | None = None):
        self.thinking = settings.ai_agent_thinking_enabled if thinking is None else thinking

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        request_id: str = "",
    ) -> LlmReply:
        if not settings.deepseek_api_key.strip():
            raise LlmError("AI助手尚未配置，请在Python服务中设置 DEEPSEEK_API_KEY")
        payload: dict[str, Any] = {
            "model": settings.deepseek_model,
            "messages": messages,
            "stream": False,
            "max_tokens": max(1, settings.deepseek_max_tokens),
            "thinking": {"type": "enabled" if self.thinking else "disabled"},
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key.strip()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(timeout=max(1, settings.deepseek_request_timeout_sec), connect=15.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{settings.deepseek_base_url}/chat/completions", headers=headers, json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LlmError("DeepSeek响应超时，请稍后重试") from exc
        except httpx.HTTPError as exc:
            LOG.warning("DeepSeek request failed request_id=%s error=%s", request_id, exc)
            raise LlmError("无法连接DeepSeek服务，请检查Python服务器网络") from exc
        if response.status_code >= 400:
            # 复用对话助手的错误码映射（401/402/429 等），对外文案保持一致。
            from backend.services.ai_assistant_service import AiAssistantService
            try:
                AiAssistantService._raise_upstream_error(response)
            except HTTPException as exc:
                raise LlmError(str(exc.detail)) from exc
        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmError("DeepSeek返回了无法识别的响应") from exc
        usage = body.get("usage") or {}
        return LlmReply(
            content=(message.get("content") or "").strip(),
            reasoning_content=message.get("reasoning_content"),
            tool_calls=list(message.get("tool_calls") or []),
            model=body.get("model") or settings.deepseek_model,
            finish_reason=choice.get("finish_reason"),
            usage={
                "promptTokens": int(usage.get("prompt_tokens") or 0),
                "completionTokens": int(usage.get("completion_tokens") or 0),
                "totalTokens": int(usage.get("total_tokens") or 0),
            },
        )
