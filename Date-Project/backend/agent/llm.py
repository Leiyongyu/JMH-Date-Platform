from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

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


@dataclass(frozen=True)
class LlmProvider:
    """模型提供方。两家都走 OpenAI 兼容的 /chat/completions，只有思考开关的参数写法不同。"""

    name: str
    label: str
    api_key: str
    base_url: str
    model: str
    key_env: str

    def thinking_fields(self, enabled: bool) -> dict[str, Any]:
        if self.name == "dashscope":
            # 百炼：enable_thinking 为非 OpenAI 标准参数，直接放在请求体顶层。
            return {"enable_thinking": enabled}
        return {"thinking": {"type": "enabled" if enabled else "disabled"}}


def current_provider() -> LlmProvider:
    if settings.ai_agent_provider == "dashscope":
        return LlmProvider("dashscope", "阿里云百炼", settings.dashscope_api_key.strip(),
                           settings.dashscope_base_url.rstrip("/"), settings.dashscope_model, "DASHSCOPE_API_KEY")
    if settings.ai_agent_provider not in ("", "deepseek"):
        LOG.warning("未知的 AI_AGENT_PROVIDER=%s，按 deepseek 处理", settings.ai_agent_provider)
    return LlmProvider("deepseek", "DeepSeek", settings.deepseek_api_key.strip(),
                       settings.deepseek_base_url.rstrip("/"), settings.deepseek_model, "DEEPSEEK_API_KEY")


def upstream_error_message(provider: LlmProvider, response: httpx.Response) -> str:
    message = ""
    try:
        body = response.json()
        error = body.get("error") or {}
        message = str(error.get("message") or body.get("message") or "").strip()
    except ValueError:
        pass
    status = response.status_code
    if status in (401, 403):
        return f"{provider.label} API Key无效或无权限，请检查 {provider.key_env}"
    if status == 402:
        return f"{provider.label}账户余额不足"
    if status == 429:
        return f"{provider.label}服务繁忙或请求频率过高，请稍后重试"
    detail = f"{provider.label}服务错误[HTTP {status}]"
    return detail + (f"：{message[:300]}" if message else "")


class AgentChatClient:
    def __init__(self, *, thinking: bool | None = None, provider: LlmProvider | None = None):
        self.thinking = settings.ai_agent_thinking_enabled if thinking is None else thinking
        self.provider = provider

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        request_id: str = "",
    ) -> LlmReply:
        provider = self.provider or current_provider()
        if not provider.api_key:
            raise LlmError(f"AI助手尚未配置，请在Python服务中设置 {provider.key_env}")
        payload: dict[str, Any] = {
            "model": provider.model,
            "messages": messages,
            "stream": False,
            "max_tokens": max(1, settings.ai_agent_max_tokens),
            **provider.thinking_fields(self.thinking),
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(timeout=max(1, settings.deepseek_request_timeout_sec), connect=15.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{provider.base_url}/chat/completions", headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LlmError(f"{provider.label}响应超时，请稍后重试") from exc
        except httpx.HTTPError as exc:
            LOG.warning("LLM request failed provider=%s request_id=%s error=%s", provider.name, request_id, exc)
            raise LlmError(f"无法连接{provider.label}服务，请检查Python服务器网络") from exc
        if response.status_code >= 400:
            LOG.warning("LLM upstream error provider=%s status=%s request_id=%s",
                        provider.name, response.status_code, request_id)
            raise LlmError(upstream_error_message(provider, response))
        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmError(f"{provider.label}返回了无法识别的响应") from exc
        usage = body.get("usage") or {}
        return LlmReply(
            content=(message.get("content") or "").strip(),
            reasoning_content=message.get("reasoning_content"),
            tool_calls=list(message.get("tool_calls") or []),
            model=body.get("model") or provider.model,
            finish_reason=choice.get("finish_reason"),
            usage={
                "promptTokens": int(usage.get("prompt_tokens") or 0),
                "completionTokens": int(usage.get("completion_tokens") or 0),
                "totalTokens": int(usage.get("total_tokens") or 0),
            },
        )

