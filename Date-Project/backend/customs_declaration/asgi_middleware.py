"""ASGI compatibility helpers for the embedded Flask application."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class EnsureContentLengthMiddleware:
    """Give WSGI an exact body length when an upstream uses chunked transfer."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = 64 * 1024 * 1024):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        header_names = {name.lower() for name, _ in headers}
        if b"content-length" in header_names and b"transfer-encoding" not in header_names:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > self.max_body_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={"error": "报关单请求体超过64MB"},
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        normalized_scope = dict(scope)
        normalized_scope["headers"] = [
            (name, value)
            for name, value in headers
            if name.lower() not in {b"content-length", b"transfer-encoding"}
        ] + [(b"content-length", str(len(body)).encode("ascii"))]

        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": bytes(body),
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        await self.app(normalized_scope, replay_receive, send)
