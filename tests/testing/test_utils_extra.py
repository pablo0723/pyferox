from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pyferox import Command, Module, Query, handle
from pyferox.testing import FakeDispatcher, create_test_app, create_test_module
from pyferox.testing.utils import _call_asgi


def test_create_test_app_without_modules() -> None:
    app = create_test_app()
    assert app.modules == []


def test_create_test_module_helper() -> None:
    module = create_test_module(name="m1")
    assert module.name == "m1"
    assert module.handlers == []


@dataclass(slots=True)
class Echo(Command):
    text: str


@dataclass(slots=True)
class GetEcho(Query):
    text: str


def test_fake_dispatcher_records_calls_and_returns_stub() -> None:
    dispatcher = FakeDispatcher()
    dispatcher.responses[Echo] = {"ok": True}
    result = asyncio.run(dispatcher.dispatch(Echo(text="x"), context=None, scoped_cache={}))
    assert result == {"ok": True}
    assert len(dispatcher.calls) == 1


@handle(GetEcho)
async def get_echo(query: GetEcho) -> dict[str, str]:
    return {"text": query.text}


def test_test_http_client_query_registration_branch() -> None:
    from pyferox.testing import TestHTTPClient

    app = create_test_app(modules=[Module(handlers=[get_echo])])
    client = TestHTTPClient(app)
    client.query("GET", "/echo/{text}", GetEcho)
    response = client.request("GET", "/echo/hello")
    assert response["status"] == 200
    assert response["json"] == {"text": "hello"}


def test_call_asgi_receive_second_chunk_branch() -> None:
    received: list[dict[str, object]] = []

    async def dummy_asgi(scope, receive, send):  # type: ignore[no-untyped-def]
        received.append(await receive())
        received.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})

    response = asyncio.run(
        _call_asgi(dummy_asgi, method="POST", path="/", body={"x": 1}, headers=[], query_string="")
    )
    assert response["status"] == 200
    assert response["json"] == {}
    assert len(received) == 2
