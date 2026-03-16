from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox.core import (
    App,
    Command,
    Event,
    HandlerNotFoundError,
    SyncPolicy,
    handle,
    map_exception_to_transport,
)
from pyferox.core.context import ExecutionContext
from pyferox.core.di import Container, Provider, ResolutionError, Scope, provider
from pyferox.core.dispatcher import Dispatcher
from pyferox.core.errors import PyFerOxError
from pyferox.core.handlers import HandlerRegistry
from pyferox.core.module import Module as RawModule, as_module
from pyferox.core.results import Streamed, Success, to_payload


def test_execution_context_service_helpers() -> None:
    context = ExecutionContext()
    context.set_service("s1", 123)
    assert context.get_service("s1") == 123
    assert context.get_service("missing", "fallback") == "fallback"


def test_container_resolution_errors_and_factory_shapes() -> None:
    container = Container()
    with pytest.raises(ResolutionError):
        container.resolve(str)

    container.register(provider(str, lambda: "value", scope=Scope.REQUEST))
    with pytest.raises(ResolutionError):
        container.resolve(str)

    container.register(Provider(key=int, scope=Scope.REQUEST, instance=5))
    with container.scope() as scoped_cache:
        assert container.resolve(int, scoped_cache) == 5

    container.register(Provider(key=float, scope=Scope.APP))
    with pytest.raises(ResolutionError):
        container.resolve(float)

    calls: list[str] = []

    def two_arg_factory(_: Container, __: dict[type[object], object] | None) -> str:
        calls.append("two")
        return "two"

    def one_arg_factory(_: Container) -> str:
        calls.append("one")
        return "one"

    container.register(provider(bytes, two_arg_factory))
    container.register(provider(bool, one_arg_factory))
    assert container.resolve(bytes) == "two"
    assert container.resolve(bool) == "one"
    assert calls == ["two", "one"]


@dataclass(slots=True)
class Ping(Command):
    value: str


def test_dispatcher_registration_and_sync_forbid_policy() -> None:
    registry = HandlerRegistry()
    container = Container()
    dispatcher = Dispatcher(registry=registry, container=container, sync_policy=SyncPolicy.FORBID)

    @handle(Ping)
    def sync_handler(message: Ping) -> str:
        return message.value

    dispatcher.register_handler(Ping, sync_handler)
    dispatcher.register_listener(Event, sync_handler)
    assert dispatcher.get_handler(Ping) is sync_handler

    with pytest.raises(TypeError):
        asyncio.run(dispatcher.dispatch(Ping(value="ok"), context=ExecutionContext(), scoped_cache={}))


def test_dispatcher_sync_handler_allowed_branch() -> None:
    dispatcher = Dispatcher(registry=HandlerRegistry(), container=Container(), sync_policy=SyncPolicy.ALLOW)

    @handle(Ping)
    def sync_handler(message: Ping) -> str:
        return message.value

    dispatcher.register_handler(Ping, sync_handler)
    result = asyncio.run(dispatcher.dispatch(Ping(value="ok"), context=ExecutionContext(), scoped_cache={}))
    assert result == "ok"


def test_dispatcher_missing_handler_and_no_param_handler() -> None:
    dispatcher = Dispatcher(registry=HandlerRegistry(), container=Container())
    with pytest.raises(HandlerNotFoundError):
        asyncio.run(dispatcher.dispatch(Ping(value="x"), context=ExecutionContext(), scoped_cache={}))

    async def invalid_handler() -> str:
        return "bad"

    with pytest.raises(TypeError):
        asyncio.run(dispatcher._invoke(invalid_handler, Ping(value="x"), ExecutionContext(), {}))


def test_dispatcher_skips_untyped_default_dependency() -> None:
    dispatcher = Dispatcher(registry=HandlerRegistry(), container=Container())

    @handle(Ping)
    async def handler(message: Ping, dep=7) -> int:  # type: ignore[no-untyped-def]
        return dep

    dispatcher.register_handler(Ping, handler)
    result = asyncio.run(dispatcher.dispatch(Ping(value="x"), context=ExecutionContext(), scoped_cache={}))
    assert result == 7


def test_module_load_requires_decorators_and_as_module() -> None:
    async def raw_handler(message: Ping) -> None:
        return None

    async def raw_listener(event: Event) -> None:
        return None

    with pytest.raises(ValueError):
        RawModule(handlers=[raw_handler]).load(HandlerRegistry())
    with pytest.raises(ValueError):
        RawModule(listeners=[raw_listener]).load(HandlerRegistry())

    module = as_module(name="users", handlers=[], listeners=[])
    assert module.name == "users"


def test_handler_registry_duplicate_registration_raises() -> None:
    registry = HandlerRegistry()

    @handle(Ping)
    async def handler(message: Ping) -> None:
        return None

    registry.register_handler(Ping, handler)
    with pytest.raises(ValueError):
        registry.register_handler(Ping, handler)


def test_to_payload_streamed_and_dataclass() -> None:
    streamed = Streamed(chunks=iter(["a"]))
    assert to_payload(streamed) is streamed
    assert to_payload(Success(data={"x": 1})) == {"data": {"x": 1}, "message": None}

    @dataclass(slots=True)
    class Out:
        value: int

    assert to_payload(Out(value=1)) == {"value": 1}
    assert to_payload({"ok": True}) == {"ok": True}


def test_app_guard_paths_and_async_on_init_error() -> None:
    app = App()
    asyncio.run(app.shutdown())
    asyncio.run(app.startup())
    asyncio.run(app.startup())
    asyncio.run(app.shutdown())

    class AwaitableInit:
        def __await__(self):
            if False:
                yield None
            return None

    def bad_init() -> AwaitableInit:
        return AwaitableInit()

    with pytest.raises(TypeError):
        App(modules=[RawModule(on_init=[bad_init])])  # type: ignore[list-item]


def test_app_publish_without_listeners() -> None:
    app = App()
    asyncio.run(app.publish(object()))


def test_app_sync_lifecycle_hooks_branch() -> None:
    seen: list[str] = []

    def startup() -> None:
        seen.append("startup")

    def shutdown() -> None:
        seen.append("shutdown")

    app = App(modules=[RawModule(on_startup=[startup], on_shutdown=[shutdown])])
    asyncio.run(app.startup())
    asyncio.run(app.shutdown())
    assert seen == ["startup", "shutdown"]


def test_app_load_module_tree_with_import_cycle() -> None:
    parent = RawModule(name="parent")
    child = RawModule(name="child")
    parent.imports.append(child)
    child.imports.append(parent)
    app = App(modules=[parent])
    assert app.modules[0].name == "parent"


def test_exception_mapping_for_framework_error_branches() -> None:
    status, payload = map_exception_to_transport(HandlerNotFoundError("missing"))
    assert status == 500
    assert payload["type"] == "handler_not_found"

    status, payload = map_exception_to_transport(PyFerOxError("boom"))
    assert status == 500
    assert payload["type"] == "framework_error"
