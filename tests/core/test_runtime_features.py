from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox import (
    App,
    Command,
    ConflictError,
    ExecutionContext,
    Module,
    ValidationError,
    handle,
    map_exception_to_transport,
)
from pyferox.core.middleware import NextCallable


@dataclass(slots=True)
class Ping(Command):
    value: str


@handle(Ping)
async def ping_handler(cmd: Ping, ctx: ExecutionContext) -> str:
    return f"{cmd.value}:{ctx.request_id}"


def test_middleware_and_hooks_and_context_injection() -> None:
    app = App(modules=[Module(handlers=[ping_handler])])
    call_order: list[str] = []

    async def pre(ctx: ExecutionContext, msg: Ping) -> None:
        call_order.append("pre")

    async def post(ctx: ExecutionContext, msg: Ping) -> None:
        call_order.append("post")

    async def middleware(ctx: ExecutionContext, msg: Ping, call_next: NextCallable) -> str:
        call_order.append("mw:before")
        result = await call_next(msg)
        call_order.append("mw:after")
        return result

    app.add_pre_hook(pre)
    app.add_post_hook(post)
    app.add_middleware(middleware)

    context = ExecutionContext(request_id="r1")
    result = asyncio.run(app.execute_with_context(Ping(value="ok"), context=context))

    assert result == "ok:r1"
    assert call_order == ["pre", "mw:before", "mw:after", "post"]


def test_lifecycle_hooks_run() -> None:
    seen: list[str] = []

    async def startup() -> None:
        seen.append("startup")

    async def shutdown() -> None:
        seen.append("shutdown")

    app = App(modules=[Module(on_startup=[startup], on_shutdown=[shutdown])])
    asyncio.run(app.startup())
    asyncio.run(app.shutdown())

    assert seen == ["startup", "shutdown"]


def test_lifespan_context_manager_runs_hooks() -> None:
    seen: list[str] = []

    async def startup() -> None:
        seen.append("startup")

    async def shutdown() -> None:
        seen.append("shutdown")

    app = App(modules=[Module(on_startup=[startup], on_shutdown=[shutdown])])

    async def run() -> None:
        async with app.lifespan():
            assert True

    asyncio.run(run())
    assert seen == ["startup", "shutdown"]


def test_module_init_hook_runs_during_load() -> None:
    seen: list[str] = []

    def on_init() -> None:
        seen.append("init")

    App(modules=[Module(on_init=[on_init])])
    assert seen == ["init"]


def test_transport_error_mapping() -> None:
    status, payload = map_exception_to_transport(ValidationError("bad input", details={"x": "required"}))
    assert status == 400
    assert payload["type"] == "validation_error"
    assert payload["details"]["x"] == "required"

    status, payload = map_exception_to_transport(ConflictError("already exists"))
    assert status == 409
    assert payload["type"] == "conflict"
    assert payload["error"] == "already exists"


@handle(Ping)
async def failing_ping_handler(cmd: Ping) -> str:
    raise ConflictError("boom")


def test_post_hook_runs_on_handler_error() -> None:
    app = App(modules=[Module(handlers=[failing_ping_handler])])
    seen: list[str] = []

    async def post(ctx: ExecutionContext, msg: Ping) -> None:
        seen.append("post")

    app.add_post_hook(post)

    with pytest.raises(ConflictError):
        asyncio.run(app.execute(Ping(value="x")))

    assert seen == ["post"]
