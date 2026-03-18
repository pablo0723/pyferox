from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox.core import (
    App,
    AppState,
    Command,
    Event,
    HandlerNotFoundError,
    LifecycleManager,
    Query,
    SyncPolicy,
    handle,
    map_exception_to_transport,
    module_diagnostics,
)
from pyferox.core.context import ExecutionContext
from pyferox.core.di import Container, Provider, ResolutionError, Scope, provider
from pyferox.core.dispatcher import Dispatcher
from pyferox.core.errors import InfrastructureError, PermissionDeniedError, PyFerOxError, UnauthorizedError
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

    status, payload = map_exception_to_transport(UnauthorizedError("login required"))
    assert status == 401
    assert payload["type"] == "unauthorized"

    status, payload = map_exception_to_transport(PermissionDeniedError("forbidden"))
    assert status == 403
    assert payload["type"] == "permission_denied"

    status, payload = map_exception_to_transport(InfrastructureError("db down"))
    assert status == 500
    assert payload["type"] == "infrastructure_error"


def test_handler_registry_introspection_helpers() -> None:
    registry = HandlerRegistry()

    @handle(Ping)
    async def ping_handler(message: Ping) -> str:
        return message.value

    @handle(Event)
    async def event_handler(event: Event) -> None:
        return None

    registry.register_handler(Ping, ping_handler)
    registry.register_listener(Event, event_handler)

    assert registry.list_handlers()[Ping] is ping_handler
    assert registry.list_listeners()[Event] == [event_handler]
    description = registry.describe()
    assert description["handlers"]["Ping"] == "ping_handler"
    assert description["listeners"]["Event"] == ["event_handler"]


def test_module_declared_contract_enforcement() -> None:
    calls: list[str] = []

    async def middleware(ctx: ExecutionContext, msg: Ping, call_next):  # type: ignore[no-untyped-def]
        calls.append("before")
        result = await call_next(msg)
        calls.append("after")
        return result

    @handle(Ping)
    async def ping_handler(message: Ping) -> str:
        return message.value

    module = RawModule(name="ping", commands=[Ping], handlers=[ping_handler], middlewares=[middleware])
    app = App(modules=[module])
    assert asyncio.run(app.execute(Ping(value="ok"))) == "ok"
    assert calls == ["before", "after"]
    info = module.diagnostics()
    assert info["commands"] == ["Ping"]
    assert info["exports"] == ["Ping"]
    assert module_diagnostics([module])[0]["name"] == "ping"

    @dataclass(slots=True)
    class Other(Command):
        value: str

    @handle(Other)
    async def wrong_handler(message: Other) -> str:
        return message.value

    with pytest.raises(ValueError):
        App(modules=[RawModule(name="bad", commands=[Ping], handlers=[wrong_handler])])

    @dataclass(slots=True)
    class Imported(Query):
        value: str

    @handle(Imported)
    async def imported_handler(message: Imported) -> str:
        return message.value

    provider_module = RawModule(
        name="provider",
        queries=[Imported],
        handlers=[imported_handler],
        exports=[Imported],
    )
    consumer_module = RawModule(name="consumer", queries=[Imported], imports=[provider_module])
    app2 = App(modules=[consumer_module])
    assert asyncio.run(app2.execute(Imported(value="x"))) == "x"
    consumer_info = consumer_module.diagnostics()
    assert consumer_info["imported_exports"] == ["Imported"]

    with pytest.raises(ValueError):
        RawModule(name="bad-export", exports=[Ping]).validate_imports()


def test_dispatcher_exception_hooks_and_result_normalization() -> None:
    dispatcher = Dispatcher(registry=HandlerRegistry(), container=Container())
    seen: list[str] = []

    @dataclass(slots=True)
    class Payload:
        value: int

    @handle(Ping)
    async def ok_handler(message: Ping):
        return Payload(value=1)

    dispatcher.register_handler(Ping, ok_handler)
    result = asyncio.run(dispatcher.dispatch(Ping(value="x"), context=ExecutionContext(), scoped_cache={}))
    assert result == {"value": 1}

    @handle(Ping)
    async def bad_handler(message: Ping) -> str:
        raise ValueError("boom")

    dispatcher.registry.message_handlers[Ping] = bad_handler

    async def on_exception(ctx: ExecutionContext, msg: Ping, exc: Exception) -> None:
        seen.append(type(exc).__name__)

    dispatcher.add_exception_hook(on_exception)
    with pytest.raises(ValueError):
        asyncio.run(dispatcher.dispatch(Ping(value="x"), context=ExecutionContext(), scoped_cache={}))
    assert seen == ["ValueError"]


def test_container_transient_and_teardown_support() -> None:
    container = Container()
    created: list[int] = []
    closed: list[int] = []

    class Resource:
        def __init__(self, value: int) -> None:
            self.value = value

    def make_resource() -> Resource:
        value = len(created) + 1
        created.append(value)
        return Resource(value)

    async def teardown_resource(resource: Resource) -> None:
        closed.append(resource.value)

    container.register(provider(Resource, make_resource, scope=Scope.TRANSIENT, teardown=teardown_resource))

    async def run() -> tuple[int, int]:
        async with container.ascope() as scoped:
            first = container.resolve(Resource, scoped)
            second = container.resolve(Resource, scoped)
            return first.value, second.value

    first, second = asyncio.run(run())
    assert first == 1
    assert second == 2
    assert closed == [2, 1]


def test_app_kernel_runtime_primitives_and_transports() -> None:
    app = App()
    assert isinstance(app.state, AppState)
    assert isinstance(app.lifecycle, LifecycleManager)

    app.register_transport("http", object())
    assert app.get_transport("http") is not None
    with pytest.raises(ValueError):
        app.register_transport("http", object())

    seen: list[str] = []

    async def startup() -> None:
        seen.append("startup")

    async def shutdown() -> None:
        seen.append("shutdown")

    app.add_startup_hook(startup)
    app.add_shutdown_hook(shutdown)
    asyncio.run(app.startup())
    asyncio.run(app.shutdown())
    assert seen == ["startup", "shutdown"]


def test_app_execute_uses_internal_transport_context() -> None:
    @handle(Ping)
    async def handler(message: Ping, context: ExecutionContext) -> str:
        return context.transport

    app = App(modules=[RawModule(handlers=[handler])])
    assert asyncio.run(app.execute(Ping(value="x"))) == "internal"
