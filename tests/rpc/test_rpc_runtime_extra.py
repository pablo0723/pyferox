from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox import App, Command, Module, ValidationError, handle
from pyferox.reliability import InMemoryIdempotencyStore, RetryPolicy
from pyferox.rpc import InMemoryRPCTransport, RPCClient, RPCRequest, RPCResponse, RPCServer


@dataclass(slots=True)
class Msg(Command):
    value: str


def test_rpc_server_and_transport_duplicate_registration() -> None:
    app = App()
    server = RPCServer(app)
    server.register("m1", Msg)
    with pytest.raises(ValueError):
        server.register("m1", Msg)

    transport = InMemoryRPCTransport()
    transport.register_service("svc", server)
    with pytest.raises(ValueError):
        transport.register_service("svc", server)


def test_rpc_server_method_not_found_and_idempotency_conflict() -> None:
    store = InMemoryIdempotencyStore()
    server = RPCServer(App(), idempotency_store=store)

    async def run() -> tuple[int, int]:
        not_found = await server.handle(RPCRequest(method="missing", payload={}))
        await store.reserve("k1")
        server.register("ok", Msg)
        conflict = await server.handle(RPCRequest(method="ok", payload={"value": "x"}, idempotency_key="k1"))
        return not_found.status_code, conflict.status_code

    not_found_status, conflict_status = asyncio.run(run())
    assert not_found_status == 404
    assert conflict_status == 409


def test_rpc_server_exception_mapping_and_idempotency_fail_status() -> None:
    @handle(Msg)
    async def boom(_: Msg) -> None:
        raise ValidationError("bad")

    store = InMemoryIdempotencyStore()
    app = App(modules=[Module(handlers=[boom])])
    server = RPCServer(app, idempotency_store=store)
    server.register("boom", Msg)

    async def run() -> tuple[int, str | None]:
        response = await server.handle(RPCRequest(method="boom", payload={"value": "x"}, idempotency_key="k2"))
        status = await store.status("k2")
        return response.status_code, status

    status_code, idem_status = asyncio.run(run())
    assert status_code == 400
    assert idem_status == "failed"


def test_rpc_transport_without_timeout_uses_direct_server_call() -> None:
    @handle(Msg)
    async def echo(cmd: Msg) -> dict[str, str]:
        await asyncio.sleep(0.01)
        return {"value": cmd.value}

    app = App(modules=[Module(handlers=[echo])])
    server = RPCServer(app)
    server.register("echo", Msg)
    transport = InMemoryRPCTransport(default_timeout_seconds=None)
    transport.register_service("svc", server)

    response = asyncio.run(transport.send("svc", RPCRequest(method="echo", payload={"value": "ok"})))
    assert response.ok is True
    assert response.data == {"value": "ok"}


def test_rpc_client_retries_then_succeeds() -> None:
    class FlakyTransport:
        def __init__(self) -> None:
            self.calls = 0

        async def send(self, service: str, request: RPCRequest) -> RPCResponse:
            self.calls += 1
            if self.calls == 1:
                return RPCResponse(ok=False, status_code=503, error={"error": "temporary"})
            return RPCResponse(ok=True, status_code=200, data={"ok": True})

    transport = FlakyTransport()
    client = RPCClient(
        transport=transport,
        service="svc",
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0),
    )

    result = asyncio.run(client.call("x", {}))
    assert result == {"ok": True}
    assert transport.calls == 2


def test_rpc_server_exception_path_without_idempotency_store() -> None:
    @handle(Msg)
    async def boom(_: Msg) -> None:
        raise RuntimeError("boom")

    app = App(modules=[Module(handlers=[boom])])
    server = RPCServer(app)
    server.register("boom", Msg)

    response = asyncio.run(server.handle(RPCRequest(method="boom", payload={"value": "x"})))
    assert response.ok is False
    assert response.status_code == 500
    assert response.error is not None


def test_rpc_transport_uses_request_timeout_when_provided() -> None:
    @handle(Msg)
    async def echo(cmd: Msg) -> dict[str, str]:
        return {"value": cmd.value}

    app = App(modules=[Module(handlers=[echo])])
    server = RPCServer(app)
    server.register("echo", Msg)
    transport = InMemoryRPCTransport(default_timeout_seconds=None)
    transport.register_service("svc", server)

    response = asyncio.run(
        transport.send(
            "svc",
            RPCRequest(method="echo", payload={"value": "ok"}, timeout_seconds=0.1),
        )
    )
    assert response.ok is True
    assert response.data == {"value": "ok"}


def test_rpc_error_payload_includes_request_id_from_metadata() -> None:
    @handle(Msg)
    async def echo(cmd: Msg) -> dict[str, str]:
        return {"value": cmd.value}

    app = App(modules=[Module(handlers=[echo])])
    server = RPCServer(app)
    server.register("echo", Msg)

    response = asyncio.run(
        server.handle(
            RPCRequest(
                method="echo",
                payload={},
                metadata={"request_id": "rpc-req-1"},
            )
        )
    )
    assert response.ok is False
    assert response.error is not None
    assert response.error.get("request_id") == "rpc-req-1"
