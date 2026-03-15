"""Handler dispatcher with pipeline support."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, get_type_hints

from pyferox.core.context import ExecutionContext
from pyferox.core.di import Container, ResolutionError
from pyferox.core.errors import HandlerNotFoundError
from pyferox.core.handlers import HandlerFn, HandlerRegistry
from pyferox.core.middleware import Middleware, compose_middlewares

Hook = Callable[[ExecutionContext, Any], Awaitable[None]]


class SyncPolicy(StrEnum):
    ALLOW = "allow"
    FORBID = "forbid"


class Dispatcher:
    def __init__(
        self,
        *,
        registry: HandlerRegistry,
        container: Container,
        middlewares: list[Middleware] | None = None,
        pre_hooks: list[Hook] | None = None,
        post_hooks: list[Hook] | None = None,
        sync_policy: SyncPolicy = SyncPolicy.ALLOW,
    ) -> None:
        self.registry = registry
        self.container = container
        self.middlewares = middlewares if middlewares is not None else []
        self.pre_hooks = pre_hooks if pre_hooks is not None else []
        self.post_hooks = post_hooks if post_hooks is not None else []
        self.sync_policy = sync_policy

    def register_handler(self, message_type: type[Any], handler: HandlerFn) -> None:
        self.registry.register_handler(message_type, handler)

    def register_listener(self, event_type: type[Any], listener: HandlerFn) -> None:
        self.registry.register_listener(event_type, listener)

    def get_handler(self, message_type: type[Any]) -> HandlerFn | None:
        return self.registry.get_handler(message_type)

    def add_middleware(self, middleware: Middleware) -> None:
        self.middlewares.append(middleware)

    def add_pre_hook(self, hook: Hook) -> None:
        self.pre_hooks.append(hook)

    def add_post_hook(self, hook: Hook) -> None:
        self.post_hooks.append(hook)

    async def dispatch(
        self,
        message: Any,
        *,
        context: ExecutionContext,
        scoped_cache: dict[type[Any], Any],
    ) -> Any:
        handler = self.registry.get_handler(type(message))
        if handler is None:
            raise HandlerNotFoundError(f"No handler registered for message type: {type(message)}")

        for hook in self.pre_hooks:
            await hook(context, message)

        async def invoke(msg: Any) -> Any:
            return await self._invoke(handler, msg, context, scoped_cache)
        call_next = compose_middlewares(middlewares=self.middlewares, context=context, terminal=invoke)

        result = await call_next(message)

        for hook in self.post_hooks:
            await hook(context, message)
        return result

    async def _invoke(
        self,
        fn: HandlerFn,
        message: Any,
        context: ExecutionContext,
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
            if annotated_type is ExecutionContext:
                kwargs[param.name] = context
                continue
            kwargs[param.name] = self.container.resolve(annotated_type, scoped_cache)

        result = fn(message, **kwargs)
        if inspect.isawaitable(result):
            return await result
        if self.sync_policy == SyncPolicy.FORBID:
            raise TypeError(f"Sync handlers are forbidden by dispatcher policy: {fn}")
        return result
