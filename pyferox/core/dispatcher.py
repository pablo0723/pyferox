"""Handler dispatcher with pipeline support."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, MutableMapping
from enum import StrEnum
from typing import Any, get_type_hints

from pyferox.core.context import ExecutionContext
from pyferox.core.di import Container, ResolutionError
from pyferox.core.errors import HandlerNotFoundError
from pyferox.core.handlers import HandlerFn, HandlerRegistry
from pyferox.core.middleware import Middleware, compose_middlewares
from pyferox.core.results import to_payload

Hook = Callable[[ExecutionContext, Any], Awaitable[None]]
ExceptionHook = Callable[[ExecutionContext, Any, Exception], Awaitable[None]]
ExceptionMapper = Callable[[Exception], Exception]


def _identity_exception_mapper(exc: Exception) -> Exception:
    return exc


def _safe_type_hints(fn: HandlerFn) -> dict[str, Any]:
    try:
        return get_type_hints(fn)
    except Exception:
        annotations = inspect.get_annotations(fn, eval_str=False)
        resolved: dict[str, Any] = {}
        globals_ns = getattr(fn, "__globals__", {})
        for name, annotation in annotations.items():
            if not isinstance(annotation, str):
                resolved[name] = annotation
                continue
            try:
                resolved[name] = eval(annotation, globals_ns, {})
            except Exception:
                resolved[name] = annotation
        return resolved


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
        exception_hooks: list[ExceptionHook] | None = None,
        exception_mapper: ExceptionMapper | None = None,
        normalize_results: bool = True,
        sync_policy: SyncPolicy = SyncPolicy.ALLOW,
    ) -> None:
        self.registry = registry
        self.container = container
        self.middlewares = middlewares if middlewares is not None else []
        self.pre_hooks = pre_hooks if pre_hooks is not None else []
        self.post_hooks = post_hooks if post_hooks is not None else []
        self.exception_hooks = exception_hooks if exception_hooks is not None else []
        self.exception_mapper = exception_mapper or _identity_exception_mapper
        self.normalize_results = normalize_results
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

    def add_exception_hook(self, hook: ExceptionHook) -> None:
        self.exception_hooks.append(hook)

    async def dispatch(
        self,
        message: Any,
        *,
        context: ExecutionContext,
        scoped_cache: MutableMapping[type[Any], Any],
    ) -> Any:
        handler = self.registry.get_handler(type(message))
        if handler is None:
            raise HandlerNotFoundError(f"No handler registered for message type: {type(message)}")

        for hook in self.pre_hooks:
            await hook(context, message)

        async def invoke(msg: Any) -> Any:
            return await self._invoke(handler, msg, context, scoped_cache)
        call_next = compose_middlewares(middlewares=self.middlewares, context=context, terminal=invoke)
        try:
            result = await call_next(message)
            return to_payload(result) if self.normalize_results else result
        except Exception as exc:
            for hook in self.exception_hooks:
                await hook(context, message, exc)
            mapped = self.exception_mapper(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        finally:
            for hook in self.post_hooks:
                await hook(context, message)

    async def _invoke(
        self,
        fn: HandlerFn,
        message: Any,
        context: ExecutionContext,
        scoped_cache: MutableMapping[type[Any], Any],
    ) -> Any:
        kwargs: dict[str, Any] = {}
        signature = inspect.signature(fn)
        hints = _safe_type_hints(fn)
        params = list(signature.parameters.values())
        if not params:
            raise TypeError(f"Handler must accept at least one argument for message/event: {fn}")

        for index, param in enumerate(params):
            if index == 0:
                continue
            annotated_type = hints.get(param.name)
            if annotated_type is None or isinstance(annotated_type, str):
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
