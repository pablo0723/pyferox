"""Lightweight dependency injection container with scoped resolution."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Scope(StrEnum):
    APP = "app"
    REQUEST = "request"
    JOB = "job"
    TRANSIENT = "transient"


class ResolutionError(LookupError):
    """Raised when a dependency cannot be resolved."""


Factory = Callable[..., Any]
Teardown = Callable[[Any], Any | Awaitable[Any]]


@dataclass(slots=True)
class Provider:
    key: type[Any]
    factory: Factory | None = None
    instance: Any = None
    scope: Scope = Scope.APP
    teardown: Teardown | None = None

    @property
    def has_instance(self) -> bool:
        return self.instance is not None


def provider(
    key: type[Any],
    factory: Factory,
    scope: Scope = Scope.APP,
    *,
    teardown: Teardown | None = None,
) -> Provider:
    return Provider(key=key, factory=factory, scope=scope, teardown=teardown)


def singleton(instance: Any, key: type[Any] | None = None) -> Provider:
    resolved_key = key or type(instance)
    return Provider(key=resolved_key, instance=instance, scope=Scope.APP)


class ScopedCache(dict[type[Any], Any]):
    def __init__(self) -> None:
        super().__init__()
        self._teardowns: list[tuple[Teardown, Any]] = []

    def add_teardown(self, teardown: Teardown, value: Any) -> None:
        self._teardowns.append((teardown, value))

    def close(self) -> None:
        for teardown, value in reversed(self._teardowns):
            result = teardown(value)
            if inspect.isawaitable(result):
                raise RuntimeError("Async teardown requires Container.ascope()")

    async def aclose(self) -> None:
        for teardown, value in reversed(self._teardowns):
            result = teardown(value)
            if inspect.isawaitable(result):
                await result


class Container:
    def __init__(self) -> None:
        self._providers: dict[type[Any], Provider] = {}
        self._singletons: dict[type[Any], Any] = {}

    def register(self, entry: Provider) -> None:
        self._providers[entry.key] = entry
        if entry.scope == Scope.APP and entry.has_instance:
            self._singletons[entry.key] = entry.instance

    @contextmanager
    def scope(self) -> ScopedCache:
        cache = ScopedCache()
        try:
            yield cache
        finally:
            cache.close()

    @asynccontextmanager
    async def ascope(self):
        cache = ScopedCache()
        try:
            yield cache
        finally:
            await cache.aclose()

    def resolve(self, key: type[Any], scoped_cache: MutableMapping[type[Any], Any] | None = None) -> Any:
        provider_entry = self._providers.get(key)
        if provider_entry is None:
            raise ResolutionError(f"No provider registered for type: {key}")

        if provider_entry.scope == Scope.APP:
            if key in self._singletons:
                return self._singletons[key]
            value = self._build(provider_entry, scoped_cache)
            self._singletons[key] = value
            return value

        if provider_entry.scope == Scope.TRANSIENT:
            value = self._build(provider_entry, scoped_cache)
            self._register_teardown(provider_entry, value, scoped_cache)
            return value

        if scoped_cache is None:
            raise ResolutionError(f"Scoped provider requires scope for type: {key}")

        if key in scoped_cache:
            return scoped_cache[key]
        value = self._build(provider_entry, scoped_cache)
        scoped_cache[key] = value
        self._register_teardown(provider_entry, value, scoped_cache)
        return value

    def _build(self, entry: Provider, scoped_cache: MutableMapping[type[Any], Any] | None) -> Any:
        if entry.has_instance:
            return entry.instance
        if entry.factory is None:
            raise ResolutionError(f"Provider for type {entry.key} has neither instance nor factory")
        signature = inspect.signature(entry.factory)
        positional = [
            param
            for param in signature.parameters.values()
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(positional) >= 2:
            return entry.factory(self, scoped_cache)
        if len(positional) == 1:
            return entry.factory(self)
        return entry.factory()

    def _register_teardown(
        self,
        entry: Provider,
        value: Any,
        scoped_cache: MutableMapping[type[Any], Any] | None,
    ) -> None:
        if entry.teardown is None:
            return
        if isinstance(scoped_cache, ScopedCache):
            scoped_cache.add_teardown(entry.teardown, value)
