from __future__ import annotations

import asyncio
from dataclasses import dataclass
from dataclasses import field
from typing import Any

import pytest

from pyferox import App, Command, ExecutionContext, PageParams, Paginated, Query, Response, SortField, Streamed
from pyferox.auth import Identity, Principal, requires
from pyferox.core import Module, handle
from pyferox.core.errors import ValidationError
from pyferox.ops import HealthRegistry
from pyferox.http.adapter import (
    HTTPAdapter,
    Route,
    _bearer_token,
    _compile_route_pattern,
    _parse_query_params,
    _read_json_body,
    _session_token_from_cookie,
    _send_stream,
    _stream_chunk_to_bytes,
)


@dataclass(slots=True)
class WhoAmI(Query):
    pass


@handle(WhoAmI)
async def who_am_i(_: WhoAmI) -> dict[str, str]:
    return {"ok": "yes"}


@dataclass(slots=True)
class ProtectedWhoAmI(Query):
    pass


@handle(ProtectedWhoAmI)
@requires("users:read")
async def protected_who_am_i(_: ProtectedWhoAmI) -> dict[str, str]:
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


def test_http_adapter_uses_handler_level_permission_declaration() -> None:
    app = App(modules=[Module(handlers=[protected_who_am_i])])
    http = HTTPAdapter(app, auth_backend=AllowAllAuthBackend())
    http.query("GET", "/me/protected", ProtectedWhoAmI)
    sent = asyncio.run(
        _call_asgi(
            http,
            scope={"type": "http", "method": "GET", "path": "/me/protected", "query_string": b"", "headers": []},
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
    assert _session_token_from_cookie("session=s-1; path=/") == "s-1"
    assert _session_token_from_cookie("foo=bar") is None
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


def test_http_adapter_openapi_generation_and_endpoint() -> None:
    app = App(modules=[Module(handlers=[create_note, who_am_i])])
    http = HTTPAdapter(app)
    http.command(
        "POST",
        "/notes",
        CreateNote,
        status_code=201,
        summary="Create note",
        tags=("notes",),
    )
    http.query("GET", "/me", WhoAmI, permission="users:read", summary="Current user")
    spec = http.openapi_spec()

    post_op = spec["paths"]["/notes"]["post"]
    assert post_op["summary"] == "Create note"
    assert post_op["requestBody"]["required"] is True
    assert post_op["tags"] == ["notes"]

    get_op = spec["paths"]["/me"]["get"]
    assert get_op["summary"] == "Current user"
    assert get_op["security"] == [{"bearerAuth": []}]
    assert get_op["x-permission"] == "users:read"

    http.enable_openapi(path="/openapi.json", title="Demo API", version="2.0")
    sent = asyncio.run(
        _call_asgi(
            http,
            scope={"type": "http", "method": "GET", "path": "/openapi.json", "query_string": b"", "headers": []},
        )
    )
    start = next(item for item in sent if item["type"] == "http.response.start")
    body = next(item for item in sent if item["type"] == "http.response.body")
    assert start["status"] == 200
    payload = body["body"].decode("utf-8")
    assert '"title": "Demo API"' in payload


def test_http_adapter_health_endpoints() -> None:
    app = App(modules=[Module(handlers=[who_am_i])])
    registry = HealthRegistry()
    registry.add_liveness("live", lambda: True)
    registry.add_readiness("db", lambda: {"ok": False, "reason": "down"})

    http = HTTPAdapter(app)
    http.enable_health_checks(registry, liveness_path="/health/live", readiness_path="/health/ready")

    live_sent = asyncio.run(
        _call_asgi(
            http,
            scope={"type": "http", "method": "GET", "path": "/health/live", "query_string": b"", "headers": []},
        )
    )
    ready_sent = asyncio.run(
        _call_asgi(
            http,
            scope={"type": "http", "method": "GET", "path": "/health/ready", "query_string": b"", "headers": []},
        )
    )

    live_start = next(item for item in live_sent if item["type"] == "http.response.start")
    ready_start = next(item for item in ready_sent if item["type"] == "http.response.start")
    assert live_start["status"] == 200
    assert ready_start["status"] == 503


@handle(CreateNote)
async def create_note_custom_response(cmd: CreateNote) -> Response:
    return Response(data={"ok": True}, status_code=202, headers={"x-result": "created"})


def test_http_adapter_response_helper_support() -> None:
    app = App(modules=[Module(handlers=[create_note_custom_response])])
    http = HTTPAdapter(app)
    http.command("POST", "/notes/custom", CreateNote, status_code=201)
    sent = asyncio.run(
        _call_asgi(
            http,
            scope={"type": "http", "method": "POST", "path": "/notes/custom", "query_string": b"", "headers": []},
            receive_events=[{"type": "http.request", "body": b'{"title":"x"}', "more_body": False}],
        )
    )
    start = next(item for item in sent if item["type"] == "http.response.start")
    assert start["status"] == 202
    assert (b"x-result", b"created") in start["headers"]


class TokenCaptureAuthBackend:
    def __init__(self) -> None:
        self.tokens: list[str | None] = []

    async def authenticate(self, token: str | None) -> Principal | None:
        self.tokens.append(token)
        return Principal(identity=Identity(subject="s1"), permissions={"p:read"})


def test_http_adapter_reads_session_token_from_cookie_and_header() -> None:
    backend = TokenCaptureAuthBackend()
    app = App(modules=[Module(handlers=[who_am_i])])
    http = HTTPAdapter(app, auth_backend=backend)
    http.query("GET", "/me-token", WhoAmI)

    asyncio.run(
        _call_asgi(
            http,
            scope={
                "type": "http",
                "method": "GET",
                "path": "/me-token",
                "query_string": b"",
                "headers": [(b"cookie", b"session=s-cookie")],
            },
        )
    )
    asyncio.run(
        _call_asgi(
            http,
            scope={
                "type": "http",
                "method": "GET",
                "path": "/me-token",
                "query_string": b"",
                "headers": [(b"x-session-token", b"s-header")],
            },
        )
    )
    assert backend.tokens == ["s-cookie", "s-header"]


@dataclass(slots=True)
class ListUsers(Query):
    page: PageParams = field(default_factory=PageParams)
    filters: dict[str, str] = field(default_factory=dict)
    sorts: list[SortField] = field(default_factory=list)


@handle(ListUsers)
async def list_users(query: ListUsers) -> list[dict[str, int | str]]:
    assert query.page.page == 2
    assert query.page.page_size == 1
    assert query.filters["role"] == "admin"
    assert query.sorts[0].field == "id"
    return [{"id": 1, "name": "A"}]


@handle(ListUsers)
async def list_users_paginated(query: ListUsers) -> Paginated:
    return Paginated(items=[{"id": 1}], total=7, page=2, page_size=1)


def test_http_adapter_list_query_conventions_and_paginated_headers() -> None:
    app = App(modules=[Module(handlers=[list_users])])
    http = HTTPAdapter(app)
    http.list_query("GET", "/users", ListUsers)
    sent = asyncio.run(
        _call_asgi(
            http,
            scope={
                "type": "http",
                "method": "GET",
                "path": "/users",
                "query_string": b"page=2&page_size=1&sort=-id&filter.role=admin",
                "headers": [],
            },
        )
    )
    start = next(item for item in sent if item["type"] == "http.response.start")
    body = next(item for item in sent if item["type"] == "http.response.body")
    assert start["status"] == 200
    assert (b"x-total-count", b"1") in start["headers"]
    assert (b"x-page", b"2") in start["headers"]
    assert (b"x-page-size", b"1") in start["headers"]
    assert body["body"] == b'{"items": [{"id": 1, "name": "A"}], "total": 1, "page": 2, "page_size": 1}'


def test_http_adapter_list_query_openapi_baseline() -> None:
    app = App(modules=[Module(handlers=[list_users_paginated])])
    http = HTTPAdapter(app)
    http.list_query("GET", "/users", ListUsers)
    spec = http.openapi_spec()
    operation = spec["paths"]["/users"]["get"]
    parameter_names = [entry["name"] for entry in operation["parameters"]]
    assert "page" in parameter_names
    assert "page_size" in parameter_names
    assert "sort" in parameter_names
    assert operation["x-filter-prefix"] == "filter."
