"""Minimal ASGI HTTP adapter that dispatches commands and queries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

from pyferox.auth import AuthBackend, PermissionChecker
from pyferox.core import App, ExecutionContext
from pyferox.core.errors import (
    AuthError,
    ForbiddenError,
    RouteConflictError,
    ValidationError,
    map_exception_to_transport,
)
from pyferox.core.results import Streamed
from pyferox.schema import parse_input, serialize_output


@dataclass(slots=True)
class Route:
    method: str
    path: str
    message_type: type[Any]
    status_code: int
    permission: str | None = None
    pattern: re.Pattern[str] = field(init=False)

    def __post_init__(self) -> None:
        self.pattern = _compile_route_pattern(self.path)

    def match(self, method: str, path: str) -> dict[str, str] | None:
        if self.method != method.upper():
            return None
        match = self.pattern.match(path)
        if match is None:
            return None
        return match.groupdict()


class HTTPAdapter:
    """ASGI app that maps HTTP requests to app commands and queries."""

    def __init__(
        self,
        app: App,
        *,
        auth_backend: AuthBackend | None = None,
        permission_checker: PermissionChecker | None = None,
    ) -> None:
        self.app = app
        self._auth_backend = auth_backend
        self._permission_checker = permission_checker
        self._routes: list[Route] = []

    def command(
        self,
        method: str,
        path: str,
        message_type: type[Any],
        status_code: int = 202,
        *,
        permission: str | None = None,
    ) -> None:
        self._register(
            Route(
                method=method.upper(),
                path=path,
                message_type=message_type,
                status_code=status_code,
                permission=permission,
            )
        )

    def query(
        self,
        method: str,
        path: str,
        message_type: type[Any],
        status_code: int = 200,
        *,
        permission: str | None = None,
    ) -> None:
        self._register(
            Route(
                method=method.upper(),
                path=path,
                message_type=message_type,
                status_code=status_code,
                permission=permission,
            )
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await _send_json(send, 500, {"error": "Only HTTP scope is supported"})
            return

        method = scope["method"].upper()
        path = scope.get("path", "/")
        route, path_params, method_allowed = self._resolve_route(method, path)
        if route is None:
            status = 405 if method_allowed else 404
            message = "Method not allowed" if method_allowed else "Route not found"
            await _send_json(send, status, {"error": message})
            return

        try:
            query_params = _parse_query_params(scope.get("query_string", b""))
            body = await _read_json_body(receive)
            payload = {**query_params, **body, **path_params}
            message = parse_input(route.message_type, payload)
            context = ExecutionContext(
                request_id=_header(scope, b"x-request-id") or ExecutionContext().request_id,
                trace_id=_header(scope, b"x-trace-id"),
                transport="http",
            )
            if self._auth_backend is not None:
                token = _bearer_token(_header(scope, b"authorization"))
                context.current_user = await self._auth_backend.authenticate(token)
            if route.permission is not None:
                if context.current_user is None:
                    raise AuthError("Authentication required")
                if self._permission_checker is None:
                    raise ForbiddenError("Permission checker is not configured")
                allowed = await self._permission_checker.allowed(context.current_user, route.permission)
                if not allowed:
                    raise ForbiddenError("Permission denied")
            result = await self.app.execute_with_context(message, context=context)
            if isinstance(result, Streamed):
                await _send_stream(send, route.status_code, result)
                return
            response_body = serialize_output(result if result is not None else {})
            await _send_json(send, route.status_code, response_body)
        except Exception as exc:
            status, payload = _map_error(exc)
            await _send_json(send, status, payload)
            return

    def _register(self, route: Route) -> None:
        for existing in self._routes:
            if existing.method == route.method and existing.path == route.path:
                raise RouteConflictError(f"Route already registered: {route.method} {route.path}")
        self._routes.append(route)

    def _resolve_route(self, method: str, path: str) -> tuple[Route | None, dict[str, str], bool]:
        method_allowed = False
        for route in self._routes:
            path_match = route.pattern.match(path)
            if path_match is None:
                continue
            if route.method == method:
                return route, path_match.groupdict(), True
            method_allowed = True
        return None, {}, method_allowed


def _compile_route_pattern(path: str) -> re.Pattern[str]:
    if not path.startswith("/"):
        raise ValueError(f"Route path must start with '/': {path}")
    escaped = re.escape(path).replace(r"\{", "{").replace(r"\}", "}")
    pattern = re.sub(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", r"(?P<\1>[^/]+)", escaped)
    return re.compile(f"^{pattern}$")


def _parse_query_params(raw: bytes) -> dict[str, str]:
    if not raw:
        return {}
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


async def _read_json_body(receive: Any) -> dict[str, Any]:
    body_chunks: list[bytes] = []
    more_body = True
    while more_body:
        event = await receive()
        if event["type"] != "http.request":
            continue
        chunk = event.get("body", b"")
        if chunk:
            body_chunks.append(chunk)
        more_body = event.get("more_body", False)

    if not body_chunks:
        return {}
    raw = b"".join(body_chunks).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid JSON body") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("JSON body must be an object")
    return parsed


def _map_error(exc: Exception) -> tuple[int, dict[str, Any]]:
    return map_exception_to_transport(exc)


def _header(scope: dict[str, Any], key: bytes) -> str | None:
    for header_key, value in scope.get("headers", []):
        if header_key.lower() == key:
            return value.decode("utf-8")
    return None


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def _send_json(send: Any, status_code: int, payload: Any) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    headers = [(b"content-type", b"application/json")]
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _send_stream(send: Any, status_code: int, result: Streamed) -> None:
    headers = [(b"content-type", result.content_type.encode("utf-8"))]
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    chunks = result.chunks
    if hasattr(chunks, "__aiter__"):
        async for chunk in chunks:  # type: ignore[union-attr]
            await send({"type": "http.response.body", "body": _stream_chunk_to_bytes(chunk), "more_body": True})
    else:
        for chunk in chunks:
            await send({"type": "http.response.body", "body": _stream_chunk_to_bytes(chunk), "more_body": True})
    await send({"type": "http.response.body", "body": b"", "more_body": False})


def _stream_chunk_to_bytes(chunk: Any) -> bytes:
    if isinstance(chunk, bytes):
        return chunk
    if isinstance(chunk, str):
        return chunk.encode("utf-8")
    if isinstance(chunk, (dict, list)):
        return json.dumps(chunk, default=str).encode("utf-8")
    return str(chunk).encode("utf-8")
