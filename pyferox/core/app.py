"""Application kernel."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from pyferox.core.context import ExecutionContext
from pyferox.core.di import Container, Provider
from pyferox.core.dispatcher import Dispatcher, ExceptionHook, Hook, SyncPolicy
from pyferox.core.handlers import HandlerRegistry
from pyferox.core.middleware import Middleware
from pyferox.core.module import Module

LifecycleHook = Any


@dataclass(slots=True)
class AppState:
    started: bool = False
    settings: dict[str, Any] = field(default_factory=dict)


class LifecycleManager:
    def __init__(self) -> None:
        self._startup_hooks: list[LifecycleHook] = []
        self._shutdown_hooks: list[LifecycleHook] = []

    def add_startup_hook(self, hook: LifecycleHook) -> None:
        self._startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: LifecycleHook) -> None:
        self._shutdown_hooks.append(hook)

    def extend_startup_hooks(self, hooks: Iterable[LifecycleHook]) -> None:
        self._startup_hooks.extend(hooks)

    def extend_shutdown_hooks(self, hooks: Iterable[LifecycleHook]) -> None:
        self._shutdown_hooks.extend(hooks)

    async def startup(self, state: AppState) -> None:
        if state.started:
            return
        for hook in self._startup_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result
        state.started = True

    async def shutdown(self, state: AppState) -> None:
        if not state.started:
            return
        for hook in reversed(self._shutdown_hooks):
            result = hook()
            if inspect.isawaitable(result):
                await result
        state.started = False


class TransportRegistry:
    def __init__(self) -> None:
        self._transports: dict[str, Any] = {}

    def register(self, name: str, transport: Any) -> None:
        if name in self._transports:
            raise ValueError(f"Transport already registered: {name}")
        self._transports[name] = transport

    def get(self, name: str) -> Any | None:
        return self._transports.get(name)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._transports)


class ProviderRegistry:
    def __init__(self, container: Container) -> None:
        self._container = container

    def register(self, entry: Provider) -> None:
        self._container.register(entry)

    def resolve(self, key: type[Any], scoped_cache: dict[type[Any], Any] | None = None) -> Any:
        return self._container.resolve(key, scoped_cache)

    def snapshot(self) -> dict[type[Any], Provider]:
        return dict(self._container._providers)


class App:
    """Main runtime for modules, DI, handlers, and events."""

    def __init__(self, *, modules: Iterable[Module] = ()) -> None:
        self.container = Container()
        self.providers = ProviderRegistry(self.container)
        self.registry = HandlerRegistry()
        self.transports = TransportRegistry()
        self.state = AppState()
        self.lifecycle = LifecycleManager()
        self.modules = list(modules)
        self._middlewares: list[Middleware] = []
        self._pre_hooks: list[Hook] = []
        self._post_hooks: list[Hook] = []
        self._exception_hooks: list[ExceptionHook] = []
        self._load_modules(self.modules)
        self.dispatcher = Dispatcher(
            registry=self.registry,
            container=self.container,
            middlewares=self._middlewares,
            pre_hooks=self._pre_hooks,
            post_hooks=self._post_hooks,
            exception_hooks=self._exception_hooks,
            sync_policy=SyncPolicy.ALLOW,
        )

    async def startup(self) -> None:
        await self.lifecycle.startup(self.state)

    async def shutdown(self) -> None:
        await self.lifecycle.shutdown(self.state)

    @asynccontextmanager
    async def lifespan(self):
        await self.startup()
        try:
            yield self
        finally:
            await self.shutdown()

    async def execute(self, message: Any) -> Any:
        context = ExecutionContext(transport="internal")
        return await self.execute_with_context(message, context=context)

    async def execute_with_context(self, message: Any, *, context: ExecutionContext) -> Any:
        async with self.container.ascope() as scoped_cache:
            return await self.dispatcher.dispatch(message, context=context, scoped_cache=scoped_cache)

    async def publish(self, event: Any) -> None:
        listeners = self.registry.get_listeners(type(event))
        if not listeners:
            return
        async with self.container.ascope() as scoped_cache:
            context = ExecutionContext(transport="event")
            for listener in listeners:
                await self.dispatcher._invoke(listener, event, context, scoped_cache)

    def add_middleware(self, middleware: Middleware) -> None:
        self.dispatcher.add_middleware(middleware)

    def add_pre_hook(self, hook: Hook) -> None:
        self.dispatcher.add_pre_hook(hook)

    def add_post_hook(self, hook: Hook) -> None:
        self.dispatcher.add_post_hook(hook)

    def add_exception_hook(self, hook: ExceptionHook) -> None:
        self.dispatcher.add_exception_hook(hook)

    def add_startup_hook(self, hook: LifecycleHook) -> None:
        self.lifecycle.add_startup_hook(hook)

    def add_shutdown_hook(self, hook: LifecycleHook) -> None:
        self.lifecycle.add_shutdown_hook(hook)

    def register_transport(self, name: str, transport: Any) -> None:
        self.transports.register(name, transport)

    def get_transport(self, name: str) -> Any | None:
        return self.transports.get(name)

    def _load_modules(self, modules: list[Module]) -> None:
        seen: set[int] = set()
        for module in modules:
            self._load_module_tree(module, seen)

    def _load_module_tree(self, module: Module, seen: set[int]) -> None:
        module_id = id(module)
        if module_id in seen:
            return
        seen.add(module_id)

        for child in module.imports:
            self._load_module_tree(child, seen)

        module.load(self.registry)
        for hook in module.on_init:
            result = hook()
            if inspect.isawaitable(result):
                raise TypeError("Module on_init hooks must be synchronous")
        for entry in module.providers:
            self.providers.register(entry)
        for middleware in getattr(module, "middlewares", []):
            self._middlewares.append(middleware)
        self.lifecycle.extend_startup_hooks(module.on_startup)
        self.lifecycle.extend_shutdown_hooks(module.on_shutdown)
