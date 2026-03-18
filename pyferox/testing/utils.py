"""Helpers for framework tests."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import Any

from pyferox.core import App, Module
from pyferox.core.di import Provider
from pyferox.http import HTTPAdapter


def create_test_app(*, modules: list[Module] | None = None) -> App:
    return App(modules=modules or [])


def create_test_module(
    *,
    name: str = "test-module",
    handlers: list[Any] | None = None,
    listeners: list[Any] | None = None,
    providers: list[Provider] | None = None,
) -> Module:
    return Module(
        name=name,
        handlers=list(handlers or []),
        listeners=list(listeners or []),
        providers=list(providers or []),
    )


class FakeDispatcher:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.responses: dict[type[Any], Any] = {}

    async def dispatch(self, message: Any, *, context: Any, scoped_cache: dict[type[Any], Any]) -> Any:
        self.calls.append(message)
        return self.responses.get(type(message))


@contextmanager
def override_dependencies(app: App, *providers: Provider):
    original_providers = dict(app.container._providers)
    original_singletons = dict(app.container._singletons)
    try:
        for entry in providers:
            app.container.register(entry)
        yield app
    finally:
        app.container._providers = original_providers
        app.container._singletons = original_singletons


class TestHTTPClient:
    __test__ = False

    def __init__(self, app: App) -> None:
        self.adapter = HTTPAdapter(app)

    def command(self, method: str, path: str, message_type: type[Any], status_code: int = 202) -> None:
        self.adapter.command(method, path, message_type, status_code=status_code)

    def query(self, method: str, path: str, message_type: type[Any], status_code: int = 200) -> None:
        self.adapter.query(method, path, message_type, status_code=status_code)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        headers: list[tuple[bytes, bytes]] | None = None,
        query_string: str = "",
    ) -> dict[str, Any]:
        return asyncio.run(
            _call_asgi(self.adapter, method=method, path=path, body=body, headers=headers or [], query_string=query_string)
        )


async def _call_asgi(
    app: HTTPAdapter,
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    headers: list[tuple[bytes, bytes]],
    query_string: str,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else b""
    sent: list[dict[str, Any]] = []
    sent_request = False

    async def receive() -> dict[str, Any]:
        nonlocal sent_request
        if sent_request:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent_request = True
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string.encode("utf-8"),
            "headers": headers,
        },
        receive,
        send,
    )

    start = next(item for item in sent if item["type"] == "http.response.start")
    chunks = [item.get("body", b"") for item in sent if item["type"] == "http.response.body"]
    raw = b"".join(chunks)
    parsed = json.loads(raw.decode("utf-8")) if raw else None
    return {"status": start["status"], "json": parsed}
