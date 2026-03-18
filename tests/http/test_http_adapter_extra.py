from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from pyferox import App, Command, ExecutionContext, Query, Streamed
from pyferox.auth import Identity, Principal
from pyferox.core import Module, handle
from pyferox.core.errors import ValidationError
from pyferox.http.adapter import (
    HTTPAdapter,
    Route,
    _bearer_token,
    _compile_route_pattern,
    _parse_query_params,
    _read_json_body,
    _send_stream,
    _stream_chunk_to_bytes,
)


@dataclass(slots=True)
class WhoAmI(Query):
    pass


@handle(WhoAmI)
async def who_am_i(_: WhoAmI) -> dict[str, str]:
    return {"ok": "yes"}


class AllowAllAuthBackend:
    async def authenticate(self, token: str | None) -> Principal | None:
        return Principal(identity=Identity(subject="s1"), permissions={"p:read"})


async def _call_asgi(
    app: HTTPAdapter,
    *,
    scope: dict[str, Any],
    receive_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    events = receive_events or [{"type": "http.request", "body": b"", "more_body": False}]
    sent: list[dict[str, Any]] = []
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        event = events[index]
        index = min(index + 1, len(events) - 1)
        return event

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def test_route_match_branches() -> None:
    route = Route(method="GET", path="/users/{user_id}", message_type=WhoAmI, status_code=200)
    assert route.match("POST", "/users/1") is None
    assert route.match("GET", "/users") is None
    assert route.match("GET", "/users/1") == {"user_id": "1"}


def test_http_adapter_rejects_non_http_scope() -> None:
    sent = asyncio.run(_call_asgi(HTTPAdapter(App()), scope={"type": "websocket"}))
    start = next(item for item in sent if item["type"] == "http.response.start")
    assert start["status"] == 500


def test_http_adapter_permission_checker_missing_branch() -> None:
    app = App(modules=[Module(handlers=[who_am_i])])
    http = HTTPAdapter(app, auth_backend=AllowAllAuthBackend())
    http.query("GET", "/me", WhoAmI, permission="p:read")
    sent = asyncio.run(
        _call_asgi(
            http,
            scope={"type": "http", "method": "GET", "path": "/me", "query_string": b"", "headers": []},
        )
    )
    start = next(item for item in sent if item["type"] == "http.response.start")
    assert start["status"] == 403


def test_compile_route_pattern_requires_leading_slash() -> None:
    with pytest.raises(ValueError):
        _compile_route_pattern("users/{id}")


def test_parse_query_params_with_values() -> None:
    assert _parse_query_params(b"a=1&b=2&b=3") == {"a": "1", "b": "3"}


def test_read_json_body_non_request_event_and_blank_payload() -> None:
    events = [
        {"type": "lifespan"},
        {"type": "http.request", "body": b"   ", "more_body": False},
    ]
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        event = events[index]
        index += 1
        return event

    assert asyncio.run(_read_json_body(receive)) == {}


def test_read_json_body_requires_object() -> None:
    events = [{"type": "http.request", "body": b"[]", "more_body": False}]

    async def receive() -> dict[str, Any]:
        return events[0]

    with pytest.raises(ValidationError):
        asyncio.run(_read_json_body(receive))


def test_bearer_token_and_stream_chunk_conversion_helpers() -> None:
    assert _bearer_token("Token abc") is None
    assert _bearer_token("Bearer token-1") == "token-1"
    assert _stream_chunk_to_bytes(b"a") == b"a"
    assert _stream_chunk_to_bytes({"x": 1}) == b'{"x": 1}'
    assert _stream_chunk_to_bytes(7) == b"7"


def test_send_stream_with_async_iterator() -> None:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def chunks():
        for part in ("a", "b"):
            yield part

    asyncio.run(_send_stream(send, 200, Streamed(chunks=chunks(), content_type="text/plain")))
    bodies = [item.get("body", b"") for item in sent if item["type"] == "http.response.body"]
    assert b"".join(bodies) == b"ab"


class CreateNote(Command):
    title: str


@handle(CreateNote)
async def create_note(cmd: CreateNote, context: ExecutionContext) -> dict[str, str]:
    return {"title": cmd.title, "transport": context.transport}


def test_http_adapter_binds_plain_command_contract_and_transport_label() -> None:
    app = App(modules=[Module(handlers=[create_note])])
    http = HTTPAdapter(app)
    http.command("POST", "/notes", CreateNote, status_code=201)
    sent = asyncio.run(
        _call_asgi(
            http,
            scope={"type": "http", "method": "POST", "path": "/notes", "query_string": b"", "headers": []},
            receive_events=[{"type": "http.request", "body": b'{"title":"hello"}', "more_body": False}],
        )
    )
    start = next(item for item in sent if item["type"] == "http.response.start")
    body = next(item for item in sent if item["type"] == "http.response.body")
    assert start["status"] == 201
    assert body["body"] == b'{"title": "hello", "transport": "http"}'
