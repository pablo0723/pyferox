from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pyferox import App, Command, Module, Query, handle, singleton
from pyferox.core.errors import NotFoundError, RouteConflictError
from pyferox.http import HTTPAdapter


class UserRepo:
    def __init__(self) -> None:
        self._next_id = 1
        self._rows: dict[int, dict[str, Any]] = {}

    async def create(self, email: str, name: str) -> int:
        user_id = self._next_id
        self._next_id += 1
        self._rows[user_id] = {"id": user_id, "email": email, "name": name}
        return user_id

    async def get(self, user_id: int) -> dict[str, Any]:
        return self._rows[user_id]


@dataclass(slots=True)
class CreateUser(Command):
    email: str
    name: str


@dataclass(slots=True)
class GetUser(Query):
    user_id: int


@handle(CreateUser)
async def create_user(cmd: CreateUser, users: UserRepo) -> dict[str, int]:
    user_id = await users.create(cmd.email, cmd.name)
    return {"id": user_id}


@handle(GetUser)
async def get_user(query: GetUser, users: UserRepo) -> dict[str, Any]:
    return await users.get(int(query.user_id))


def test_http_adapter_command_and_query() -> None:
    app = App(modules=[Module(handlers=[create_user, get_user], providers=[singleton(UserRepo())])])
    http = HTTPAdapter(app)
    http.command("POST", "/users", CreateUser, status_code=201)
    http.query("GET", "/users/{user_id}", GetUser)

    create_response = asyncio.run(
        _call_asgi(
            http,
            method="POST",
            path="/users",
            body={"email": "ann@example.com", "name": "Ann"},
        )
    )
    assert create_response["status"] == 201
    assert create_response["json"] == {"id": 1}

    fetch_response = asyncio.run(_call_asgi(http, method="GET", path="/users/1"))
    assert fetch_response["status"] == 200
    assert fetch_response["json"] == {"id": 1, "email": "ann@example.com", "name": "Ann"}


def test_http_adapter_returns_404_for_unknown_route() -> None:
    app = App()
    http = HTTPAdapter(app)
    response = asyncio.run(_call_asgi(http, method="GET", path="/missing"))
    assert response["status"] == 404


def test_http_adapter_returns_405_for_wrong_method() -> None:
    app = App()
    http = HTTPAdapter(app)
    http.query("GET", "/users/{user_id}", GetUser)
    response = asyncio.run(_call_asgi(http, method="POST", path="/users/1"))
    assert response["status"] == 405


def test_http_adapter_route_conflict() -> None:
    app = App()
    http = HTTPAdapter(app)
    http.query("GET", "/users/{user_id}", GetUser)
    try:
        http.query("GET", "/users/{user_id}", GetUser)
        assert False, "expected conflict"
    except RouteConflictError:
        assert True


@handle(GetUser)
async def not_found_handler(query: GetUser) -> dict[str, Any]:
    raise NotFoundError("user missing")


def test_http_adapter_maps_domain_errors() -> None:
    app = App(modules=[Module(handlers=[not_found_handler])])
    http = HTTPAdapter(app)
    http.query("GET", "/users/{user_id}", GetUser)
    response = asyncio.run(_call_asgi(http, method="GET", path="/users/1"))
    assert response["status"] == 404
    assert response["json"]["error"] == "user missing"


async def _call_asgi(
    app: HTTPAdapter,
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    query_string: str = "",
) -> dict[str, Any]:
    payload = b""
    if body is not None:
        payload = json.dumps(body).encode("utf-8")

    sent: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        request_sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string.encode("utf-8"),
            "headers": [],
        },
        receive,
        send,
    )

    start = next(item for item in sent if item["type"] == "http.response.start")
    chunks = [item.get("body", b"") for item in sent if item["type"] == "http.response.body"]
    raw = b"".join(chunks)
    parsed = json.loads(raw.decode("utf-8")) if raw else None
    return {"status": start["status"], "json": parsed}
