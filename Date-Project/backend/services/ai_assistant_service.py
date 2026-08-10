from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from backend.config import settings
from backend.repositories.ai_conversation_repository import (
    ConversationNotFoundError,
    ai_conversation_repository,
)
from backend.schemas.ai_requests import AiChatRequest, AiPageContext


LOG = logging.getLogger(__name__)


class AiAssistantService:
    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.deepseek_api_key.strip()),
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "thinkingEnabled": settings.deepseek_thinking_enabled,
        }

    def list_conversations(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        return ai_conversation_repository.list_for_user(user_id, limit)

    def create_conversation(
        self, user_id: int, username: str, title: str = "新对话"
    ) -> dict[str, Any]:
        return ai_conversation_repository.create(user_id, username, title)

    def get_conversation(self, user_id: int, conversation_id: str) -> dict[str, Any]:
        try:
            return ai_conversation_repository.get_detail(user_id, conversation_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="对话不存在或无权访问") from exc

    def delete_conversation(self, user_id: int, conversation_id: str) -> None:
        if not ai_conversation_repository.delete(user_id, conversation_id):
            raise HTTPException(status_code=404, detail="对话不存在或无权访问")

    async def chat(
        self,
        request: AiChatRequest,
        user_id: int,
        username: str,
        request_id: str,
    ) -> dict[str, Any]:
        if not settings.deepseek_api_key.strip():
            raise HTTPException(
                status_code=503,
                detail="AI助手尚未配置，请在Python服务中设置 DEEPSEEK_API_KEY",
            )

        conversation_id = str(request.conversation_id)
        title = self._message_title(request.message)
        try:
            user_message_id = await run_in_threadpool(
                ai_conversation_repository.append_message,
                user_id,
                username,
                conversation_id,
                "user",
                request.message,
                request_id=request_id,
                first_message_title=title,
            )
            history = await run_in_threadpool(
                ai_conversation_repository.context_messages,
                user_id,
                conversation_id,
                29,
            )
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="对话不存在或无权访问") from exc

        try:
            result = await self._request_deepseek(
                history, request.page_context, request_id
            )
        except HTTPException as exc:
            await self._save_error_message(
                user_id, username, conversation_id, request_id, exc
            )
            raise

        usage = result["usage"]
        assistant_message_id = await run_in_threadpool(
            ai_conversation_repository.append_message,
            user_id,
            username,
            conversation_id,
            "assistant",
            result["content"],
            request_id=request_id,
            model=result["model"],
            prompt_tokens=usage["promptTokens"],
            completion_tokens=usage["completionTokens"],
            total_tokens=usage["totalTokens"],
        )
        conversation = await run_in_threadpool(
            ai_conversation_repository.get_summary, user_id, conversation_id
        )
        return {
            **result,
            "conversation": conversation,
            "userMessageId": str(user_message_id),
            "assistantMessageId": str(assistant_message_id),
        }

    async def _save_error_message(
        self,
        user_id: int,
        username: str,
        conversation_id: str,
        request_id: str,
        error: HTTPException,
    ) -> None:
        try:
            await run_in_threadpool(
                ai_conversation_repository.append_message,
                user_id,
                username,
                conversation_id,
                "assistant",
                str(error.detail),
                request_id=request_id,
                is_error=True,
                model=settings.deepseek_model,
            )
        except Exception:
            LOG.exception(
                "Failed to persist AI error message request_id=%s", request_id
            )

    async def _request_deepseek(
        self,
        messages: list[dict[str, str]],
        page_context: AiPageContext | None,
        request_id: str,
    ) -> dict[str, Any]:
        payload = self._build_payload(messages, page_context)
        timeout = httpx.Timeout(
            timeout=max(1, settings.deepseek_request_timeout_sec),
            connect=15.0,
        )
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key.strip()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{settings.deepseek_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504, detail="DeepSeek响应超时，请稍后重试"
            ) from exc
        except httpx.HTTPError as exc:
            LOG.warning("DeepSeek request failed request_id=%s error=%s", request_id, exc)
            raise HTTPException(
                status_code=502, detail="无法连接DeepSeek服务，请检查Python服务器网络"
            ) from exc

        if response.status_code >= 400:
            self._raise_upstream_error(response)

        try:
            body = response.json()
            choice = body["choices"][0]
            content = (choice["message"].get("content") or "").strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            LOG.warning(
                "Invalid DeepSeek response request_id=%s status=%s",
                request_id,
                response.status_code,
            )
            raise HTTPException(
                status_code=502, detail="DeepSeek返回了无法识别的响应"
            ) from exc

        if not content:
            raise HTTPException(status_code=502, detail="DeepSeek未返回有效回答")

        usage = body.get("usage") or {}
        LOG.info(
            "AI chat completed request_id=%s model=%s prompt_tokens=%s completion_tokens=%s",
            request_id,
            body.get("model") or settings.deepseek_model,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        return {
            "content": content,
            "model": body.get("model") or settings.deepseek_model,
            "finishReason": choice.get("finish_reason"),
            "usage": {
                "promptTokens": usage.get("prompt_tokens", 0),
                "completionTokens": usage.get("completion_tokens", 0),
                "totalTokens": usage.get("total_tokens", 0),
            },
        }

    def _build_payload(
        self,
        conversation_messages: list[dict[str, str]],
        page_context: AiPageContext | None = None,
    ) -> dict[str, Any]:
        system_prompt = settings.deepseek_system_prompt.strip()
        if page_context:
            page_parts = []
            if page_context.title:
                page_parts.append(f"页面标题：{page_context.title}")
            if page_context.path:
                page_parts.append(f"页面路径：{page_context.path}")
            if page_parts:
                system_prompt += "\n当前用户所在ERP页面：" + "；".join(page_parts)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(self._trim_context(conversation_messages))
        return {
            "model": settings.deepseek_model,
            "messages": messages,
            "stream": False,
            "max_tokens": max(1, settings.deepseek_max_tokens),
            "thinking": {
                "type": "enabled" if settings.deepseek_thinking_enabled else "disabled"
            },
        }

    @staticmethod
    def _trim_context(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        total_chars = 0
        for message in reversed(messages[-29:]):
            content = str(message.get("content") or "").strip()
            role = str(message.get("role") or "")
            if not content or role not in {"user", "assistant"}:
                continue
            if selected and total_chars + len(content) > 50000:
                break
            selected.append({"role": role, "content": content})
            total_chars += len(content)
        selected.reverse()
        return selected

    @staticmethod
    def _message_title(message: str) -> str:
        normalized = " ".join(message.split())
        return normalized[:40] + ("…" if len(normalized) > 40 else "")

    @staticmethod
    def _raise_upstream_error(response: httpx.Response) -> None:
        message = ""
        try:
            body = response.json()
            error = body.get("error") or {}
            message = str(error.get("message") or body.get("message") or "").strip()
        except ValueError:
            message = ""

        if response.status_code in {401, 403}:
            detail = "DeepSeek API Key无效或无权限"
        elif response.status_code == 402:
            detail = "DeepSeek账户余额不足"
        elif response.status_code == 429:
            detail = "DeepSeek服务繁忙或请求频率过高，请稍后重试"
        else:
            detail = f"DeepSeek服务错误[HTTP {response.status_code}]"
            if message:
                detail += f"：{message[:300]}"
        raise HTTPException(status_code=502, detail=detail)


ai_assistant_service = AiAssistantService()
