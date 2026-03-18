from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox.core import App, Command, Query, handle
from pyferox.core.app import ProviderRegistry, TransportRegistry
from pyferox.core.di import Container, Scope, ScopedCache, provider
from pyferox.core.dispatcher import Dispatcher, _safe_type_hints
from pyferox.core.errors import FrameworkError, InfrastructureError, normalize_execution_exception
from pyferox.core.handlers import HandlerRegistry
from pyferox.core.context import ExecutionContext
from pyferox.core.messages import contract, get_contract_metadata
from pyferox.core.module import Module
from pyferox.core.pagination import parse_sort


def test_transport_and_provider_registry_snapshot_and_resolve() -> None:
    t = TransportRegistry()
    t.register("http", object())
    assert "http" in t.snapshot()

    container = Container()
    p = ProviderRegistry(container)
    p.register(provider(str, lambda: "x"))
    assert p.resolve(str) == "x"
    assert str in p.snapshot()


def test_safe_type_hints_fallback_branches(monkeypatch) -> None:
    def fn(x):  # type: ignore[no-untyped-def]
        return x

    fn.__annotations__ = {"x": int, "y": "MissingType"}  # type: ignore[attr-defined]
    monkeypatch.setattr("pyferox.core.dispatcher.get_type_hints", lambda _: (_ for _ in ()).throw(RuntimeError("x")))
    hints = _safe_type_hints(fn)  # type: ignore[arg-type]
    assert hints["x"] is int
    assert isinstance(hints["y"], str)


def test_dispatcher_exception_mapper_branch() -> None:
    @dataclass(slots=True)
    class Msg(Command):
        value: str

    @handle(Msg)
    async def boom(_: Msg) -> None:
        raise ValueError("x")

    registry = HandlerRegistry()
    registry.register_handler(Msg, boom)
    dispatcher = Dispatcher(
        registry=registry,
        container=Container(),
        exception_mapper=lambda exc: InfrastructureError("mapped"),
    )

    with pytest.raises(InfrastructureError):
        asyncio.run(dispatcher.dispatch(Msg(value="x"), context=ExecutionContext(), scoped_cache={}))


def test_normalize_execution_exception_and_contract_helpers() -> None:
    framework_exc = FrameworkError("x")
    assert normalize_execution_exception(framework_exc) is framework_exc
    assert isinstance(normalize_execution_exception(ValueError("x")), InfrastructureError)

    with pytest.raises(TypeError):
        contract(tag="x")(str)  # type: ignore[arg-type]

    assert get_contract_metadata(str) == {}  # type: ignore[arg-type]


def test_module_load_undeclared_handler_contract_and_parse_sort_blank() -> None:
    @dataclass(slots=True)
    class Declared(Command):
        value: str

    @dataclass(slots=True)
    class Undeclared(Query):
        value: str

    @handle(Undeclared)
    async def h(_: Undeclared) -> None:
        return None

    module = Module(commands=[Declared], handlers=[h])
    with pytest.raises(ValueError):
        module.load(HandlerRegistry())

    assert parse_sort(" , ,+a")[-1].field == "a"


def test_execution_context_keeps_explicit_correlation_id() -> None:
    context = ExecutionContext(request_id="r1", trace_id="t1", correlation_id="c1")
    assert context.correlation_id == "c1"


def test_module_load_rejects_undeclared_handler_after_import_validation_passes() -> None:
    @dataclass(slots=True)
    class Declared(Command):
        value: str

    @dataclass(slots=True)
    class Extra(Command):
        value: str

    @handle(Declared)
    async def declared_handler(_: Declared) -> None:
        return None

    @handle(Extra)
    async def extra_handler(_: Extra) -> None:
        return None

    module = Module(commands=[Declared], handlers=[declared_handler, extra_handler])
    with pytest.raises(ValueError):
        module.load(HandlerRegistry())


def test_scoped_cache_close_and_aclose_teardown_branches() -> None:
    class AwaitableTeardown:
        def __await__(self):
            if False:
                yield None
            return None

    def sync_teardown(value: int) -> None:
        sync_seen.append(value)

    sync_seen: list[int] = []
    second_cache = ScopedCache()
    second_cache.add_teardown(sync_teardown, 1)
    second_cache.add_teardown(sync_teardown, 2)
    second_cache.close()
    assert sync_seen == [2, 1]

    def awaitable_teardown(_: object) -> AwaitableTeardown:
        return AwaitableTeardown()

    third_cache = ScopedCache()
    third_cache.add_teardown(awaitable_teardown, object())
    with pytest.raises(RuntimeError):
        third_cache.close()

    fourth_cache = ScopedCache()

    def last_sync_teardown(value: int) -> None:
        last_sync_seen.append(value)

    last_sync_seen: list[int] = []
    fourth_cache.add_teardown(last_sync_teardown, 3)
    asyncio.run(fourth_cache.aclose())
    assert last_sync_seen == [3]


def test_container_transient_teardown_skips_plain_dict_scope_cache() -> None:
    class Resource:
        pass

    container = Container()
    torn_down: list[str] = []

    def build() -> Resource:
        return Resource()

    def teardown(_: Resource) -> None:
        torn_down.append("x")

    container.register(provider(Resource, build, scope=Scope.TRANSIENT, teardown=teardown))
    value = container.resolve(Resource, {})
    assert isinstance(value, Resource)
    assert torn_down == []
