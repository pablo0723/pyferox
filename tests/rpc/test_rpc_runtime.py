from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox import App, Command, Module, handle
from pyferox.reliability import InMemoryIdempotencyStore
from pyferox.rpc import InMemoryRPCTransport, RPCClient, RPCError, RPCServer


@dataclass(slots=True)
class Echo(Command):
    value: str


def test_rpc_client_server_success_roundtrip() -> None:
    @handle(Echo)
    async def echo(cmd: Echo) -> dict[str, str]:
        return {"echo": cmd.value}

    app = App(modules=[Module(handlers=[echo])])
    server = RPCServer(app)
    server.register("echo", Echo)
    transport = InMemoryRPCTransport()
    transport.register_service("users", server)
    client = RPCClient(transport=transport, service="users")

    result = asyncio.run(client.call("echo", {"value": "ok"}))
    assert result == {"echo": "ok"}


def test_rpc_timeout_and_error_mapping() -> None:
    @handle(Echo)
    async def slow(_: Echo) -> dict[str, str]:
        await asyncio.sleep(0.05)
        return {"ok": "x"}

    app = App(modules=[Module(handlers=[slow])])
    server = RPCServer(app)
    server.register("slow", Echo)
    transport = InMemoryRPCTransport(default_timeout_seconds=0.01)
    transport.register_service("users", server)
    client = RPCClient(transport=transport, service="users")

    with pytest.raises(RPCError) as exc_info:
        asyncio.run(client.call("slow", {"value": "x"}))
    assert exc_info.value.status_code == 504


def test_rpc_idempotency_key_caches_success_result() -> None:
    calls = {"count": 0}

    @handle(Echo)
    async def echo(cmd: Echo) -> dict[str, str]:
        calls["count"] += 1
        return {"echo": cmd.value}

    app = App(modules=[Module(handlers=[echo])])
    server = RPCServer(app, idempotency_store=InMemoryIdempotencyStore())
    server.register("echo", Echo)
    transport = InMemoryRPCTransport()
    transport.register_service("users", server)
    client = RPCClient(transport=transport, service="users")

    async def run() -> tuple[dict[str, str], dict[str, str]]:
        first = await client.call("echo", {"value": "1"}, idempotency_key="k1")
        second = await client.call("echo", {"value": "1"}, idempotency_key="k1")
        return first, second

    first, second = asyncio.run(run())
    assert first == {"echo": "1"}
    assert second == {"echo": "1"}
    assert calls["count"] == 1


def test_rpc_method_not_found_raises_rpc_error() -> None:
    transport = InMemoryRPCTransport()
    client = RPCClient(transport=transport, service="missing")

    with pytest.raises(RPCError) as exc_info:
        asyncio.run(client.call("x", {}))
    assert exc_info.value.status_code == 404
