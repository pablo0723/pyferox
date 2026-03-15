"""Application kernel."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

from pyferox.core.context import ExecutionContext
from pyferox.core.di import Container
from pyferox.core.dispatcher import Dispatcher, Hook, SyncPolicy
from pyferox.core.handlers import HandlerRegistry
from pyferox.core.middleware import Middleware
from pyferox.core.module import Module


class App:
    """Main runtime for modules, DI, handlers, and events."""

    def __init__(self, *, modules: Iterable[Module] = ()) -> None:
        self.container = Container()
        self.registry = HandlerRegistry()
        self.modules = list(modules)
        self._started = False
        self._startup_hooks: list[Any] = []
        self._shutdown_hooks: list[Any] = []
        self._middlewares: list[Middleware] = []
        self._pre_hooks: list[Hook] = []
        self._post_hooks: list[Hook] = []
        self._load_modules(self.modules)
        self.dispatcher = Dispatcher(
            registry=self.registry,
            container=self.container,
            middlewares=self._middlewares,
            pre_hooks=self._pre_hooks,
            post_hooks=self._post_hooks,
            sync_policy=SyncPolicy.ALLOW,
        )

    async def startup(self) -> None:
        if self._started:
            return
        for hook in self._startup_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result
        self._started = True

    async def shutdown(self) -> None:
        if not self._started:
            return
        for hook in reversed(self._shutdown_hooks):
            result = hook()
            if inspect.isawaitable(result):
                await result
        self._started = False

    async def execute(self, message: Any) -> Any:
        context = ExecutionContext()
        return await self.execute_with_context(message, context=context)

    async def execute_with_context(self, message: Any, *, context: ExecutionContext) -> Any:
        with self.container.scope() as scoped_cache:
            return await self.dispatcher.dispatch(message, context=context, scoped_cache=scoped_cache)

    async def publish(self, event: Any) -> None:
        listeners = self.registry.get_listeners(type(event))
        if not listeners:
            return
        with self.container.scope() as scoped_cache:
            context = ExecutionContext()
            for listener in listeners:
                await self.dispatcher._invoke(listener, event, context, scoped_cache)

    def add_middleware(self, middleware: Middleware) -> None:
        self.dispatcher.add_middleware(middleware)

    def add_pre_hook(self, hook: Hook) -> None:
        self.dispatcher.add_pre_hook(hook)

    def add_post_hook(self, hook: Hook) -> None:
        self.dispatcher.add_post_hook(hook)

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
            self.container.register(entry)
        self._startup_hooks.extend(module.on_startup)
        self._shutdown_hooks.extend(module.on_shutdown)
