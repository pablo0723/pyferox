"""Application kernel."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any, get_type_hints

from pyferox.core.di import Container, ResolutionError
from pyferox.core.handlers import HandlerFn, HandlerRegistry
from pyferox.core.module import Module


class App:
    """Main runtime for modules, DI, handlers, and events."""

    def __init__(self, *, modules: Iterable[Module] = ()) -> None:
        self.container = Container()
        self.registry = HandlerRegistry()
        self.modules = list(modules)
        self._load_modules(self.modules)

    async def execute(self, message: Any) -> Any:
        handler = self.registry.get_handler(type(message))
        if handler is None:
            raise LookupError(f"No handler registered for message type: {type(message)}")
        with self.container.scope() as scoped_cache:
            return await self._invoke(handler, message, scoped_cache)

    async def publish(self, event: Any) -> None:
        listeners = self.registry.get_listeners(type(event))
        if not listeners:
            return
        with self.container.scope() as scoped_cache:
            for listener in listeners:
                await self._invoke(listener, event, scoped_cache)

    def _load_modules(self, modules: list[Module]) -> None:
        for module in modules:
            module.load(self.registry)
            for entry in module.providers:
                self.container.register(entry)

    async def _invoke(
        self,
        fn: HandlerFn,
        message: Any,
        scoped_cache: dict[type[Any], Any],
    ) -> Any:
        kwargs: dict[str, Any] = {}
        signature = inspect.signature(fn)
        hints = get_type_hints(fn)

        params = list(signature.parameters.values())
        if not params:
            raise TypeError(f"Handler must accept at least one argument for message/event: {fn}")

        for index, param in enumerate(params):
            if index == 0:
                continue
            annotated_type = hints.get(param.name)
            if annotated_type is None:
                if param.default is not inspect.Parameter.empty:
                    continue
                raise ResolutionError(
                    f"Dependency parameter '{param.name}' in {fn} must have a type annotation"
                )
            kwargs[param.name] = self.container.resolve(annotated_type, scoped_cache)

        return await fn(message, **kwargs)

