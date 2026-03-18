from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from pyferox import App, Command, Module, PageParams, Paginated, Query, Response, SortField
from pyferox.core import handle
from pyferox.http.adapter import (
    HTTPAdapter,
    _apply_list_query_conventions,
    _coerce_int_or_none,
    _message_page,
    _normalize_list_result,
    _schema_for_annotation,
    _schema_for_type,
)
from pyferox.schema import schema_metadata


async def _call_asgi(
    app: HTTPAdapter,
    *,
    method: str,
    path: str,
    query_string: bytes = b"",
    body: bytes = b"",
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    done = False

    async def receive() -> dict[str, Any]:
        nonlocal done
        if done:
            return {"type": "http.request", "body": b"", "more_body": False}
        done = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(
        {"type": "http", "method": method, "path": path, "query_string": query_string, "headers": []},
        receive,
        send,
    )
    return sent


@dataclass(slots=True)
class ListUsers(Query):
    page: PageParams = field(default_factory=PageParams)
    filters: dict[str, str] = field(default_factory=dict)
    sorts: list[SortField] = field(default_factory=list)


@handle(ListUsers)
async def list_users_response(_: ListUsers) -> Response:
    return Response(
        data=Paginated(items=[{"id": 1}], total=1, page=1, page_size=10),
        status_code=200,
    )


def test_http_adapter_response_paginated_headers_in_list_mode() -> None:
    app = App(modules=[Module(handlers=[list_users_response])])
    http = HTTPAdapter(app)
    http.list_query("GET", "/users", ListUsers)
    sent = asyncio.run(_call_asgi(http, method="GET", path="/users"))
    start = next(item for item in sent if item["type"] == "http.response.start")
    assert (b"x-total-count", b"1") in start["headers"]


@schema_metadata(title="Create", description="Create command")
class Create(Command):
    name: str


@handle(Create)
async def create_handler(cmd: Create) -> dict[str, str]:
    return {"name": cmd.name}


def test_http_openapi_metadata_and_description_fields() -> None:
    app = App(modules=[Module(handlers=[create_handler])])
    http = HTTPAdapter(app)
    http.route("POST", "/create", Create, kind="command", summary="s", description="d", tags=("x",))
    spec = http.openapi_spec()
    op = spec["paths"]["/create"]["post"]
    assert op["description"] == "d"
    assert op["requestBody"]["required"] is True


def test_http_route_registration_without_existing_handler_permission_lookup_branch() -> None:
    class Raw(Query):
        value: str

    http = HTTPAdapter(App())
    http.query("GET", "/raw", Raw)
    assert len(http._routes) == 1  # type: ignore[attr-defined]


def test_http_schema_helper_annotation_branches() -> None:
    assert _schema_for_annotation(tuple[int])["type"] == "array"
    assert _schema_for_annotation(dict[str, int])["type"] == "object"
    assert _schema_for_annotation(Any) == {"type": "object"}
    optional_schema = _schema_for_annotation(int | None)
    assert optional_schema["nullable"] is True


def test_http_schema_for_type_required_and_private_skip() -> None:
    @dataclass(slots=True)
    class D:
        id: int
        name: str = "x"

    class C:
        a: int
        _hidden: str

    d_schema = _schema_for_type(D)
    c_schema = _schema_for_type(C)
    assert "id" in d_schema["required"]
    assert "_hidden" not in c_schema["properties"]


def test_http_list_conventions_and_helpers_edge_branches() -> None:
    normalized = _apply_list_query_conventions(
        route=type("R", (), {"max_page_size": 100})(),
        message_type=ListUsers,
        query_params={"filter.x": "1"},
    )
    assert normalized["filters"]["x"] == "1"

    assert _coerce_int_or_none(None, key="page") is None
    with pytest.raises(Exception):
        _coerce_int_or_none("bad", key="page")

    page = PageParams(page=2, page_size=3)
    paginated = Paginated(items=[], total=0, page=2, page_size=3)
    assert _normalize_list_result(paginated, type("M", (), {"page": page})()) is paginated
    assert _normalize_list_result("x", object()) == "x"
    assert _message_page(object()) == PageParams()


class SearchUsers(Query):
    page: PageParams = field(default_factory=PageParams)
    filters: dict[str, str] = field(default_factory=dict)
    sorts: list[SortField] = field(default_factory=list)
    search: str


class NonPageListUsers(Query):
    page: int
    sorts: list[SortField]


def test_http_list_query_permission_resolution_branches() -> None:
    http = HTTPAdapter(App())
    http.list_query("GET", "/explicit", ListUsers, permission="users:read")
    http.list_query("GET", "/implicit", ListUsers)

    assert http._routes[0].permission == "users:read"  # type: ignore[attr-defined]
    assert http._routes[1].permission is None  # type: ignore[attr-defined]


def test_http_openapi_list_query_includes_non_reserved_query_properties() -> None:
    http = HTTPAdapter(App())
    http.list_query("GET", "/search", SearchUsers)
    operation = http.openapi_spec()["paths"]["/search"]["get"]
    names = [item["name"] for item in operation["parameters"]]
    assert "search" in names


def test_http_schema_helpers_additional_branches(monkeypatch) -> None:
    class Model:
        value: int = 1

    schema = _schema_for_type(Model)
    assert "value" not in schema["required"]

    monkeypatch.setattr("pyferox.http.adapter.get_origin", lambda _: Any)
    assert _schema_for_annotation(object()) == {}


def test_http_list_conventions_without_page_params_or_filters() -> None:
    normalized = _apply_list_query_conventions(
        route=type("R", (), {"max_page_size": 100})(),
        message_type=NonPageListUsers,
        query_params={"page": "2", "sort": "name", "filter.role": "admin"},
    )
    assert normalized["page"] == "2"
    assert normalized["sorts"][0]["field"] == "name"
    assert "filters" not in normalized
    assert normalized["filter.role"] == "admin"
