"""Lightweight dependency injection container with scoped resolution."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Scope(StrEnum):
    APP = "app"
    REQUEST = "request"
    JOB = "job"


class ResolutionError(LookupError):
    """Raised when a dependency cannot be resolved."""


Factory = Callable[..., Any]


@dataclass(slots=True)
class Provider:
    key: type[Any]
    factory: Factory | None = None
    instance: Any = None
    scope: Scope = Scope.APP

    @property
    def has_instance(self) -> bool:
        return self.instance is not None


def provider(key: type[Any], factory: Factory, scope: Scope = Scope.APP) -> Provider:
    return Provider(key=key, factory=factory, scope=scope)


def singleton(instance: Any, key: type[Any] | None = None) -> Provider:
    resolved_key = key or type(instance)
    return Provider(key=resolved_key, instance=instance, scope=Scope.APP)


class Container:
    def __init__(self) -> None:
        self._providers: dict[type[Any], Provider] = {}
        self._singletons: dict[type[Any], Any] = {}

    def register(self, entry: Provider) -> None:
        self._providers[entry.key] = entry
        if entry.scope == Scope.APP and entry.has_instance:
            self._singletons[entry.key] = entry.instance

    @contextmanager
    def scope(self) -> dict[type[Any], Any]:
        cache: dict[type[Any], Any] = {}
        yield cache

    def resolve(self, key: type[Any], scoped_cache: dict[type[Any], Any] | None = None) -> Any:
        provider_entry = self._providers.get(key)
        if provider_entry is None:
            raise ResolutionError(f"No provider registered for type: {key}")

        if provider_entry.scope == Scope.APP:
            if key in self._singletons:
                return self._singletons[key]
            value = self._build(provider_entry, scoped_cache)
            self._singletons[key] = value
            return value

        if scoped_cache is None:
            raise ResolutionError(f"Scoped provider requires scope for type: {key}")

        if key in scoped_cache:
            return scoped_cache[key]
        value = self._build(provider_entry, scoped_cache)
        scoped_cache[key] = value
        return value

    def _build(self, entry: Provider, scoped_cache: dict[type[Any], Any] | None) -> Any:
        if entry.has_instance:
            return entry.instance
        if entry.factory is None:
            raise ResolutionError(f"Provider for type {entry.key} has neither instance nor factory")
        try:
            return entry.factory(self, scoped_cache)
        except TypeError:
            try:
                return entry.factory(self)
            except TypeError:
                return entry.factory()

