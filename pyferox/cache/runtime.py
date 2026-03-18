"""Cache abstractions and in-memory implementation with TTL support."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
InvalidationHook = Callable[[str], Awaitable[None] | None]


class Cache(Protocol):
    async def get(self, key: str, default: T | None = None) -> Any | T | None:
        ...

    async def set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...

    async def exists(self, key: str) -> bool:
        ...

    async def clear(self) -> None:
        ...


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    expires_at: float | None = None

    def is_expired(self, now: float) -> bool:
        return self.expires_at is not None and self.expires_at <= now


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._invalidation_hooks: list[InvalidationHook] = []

    def add_invalidation_hook(self, hook: InvalidationHook) -> None:
        self._invalidation_hooks.append(hook)

    async def get(self, key: str, default: T | None = None) -> Any | T | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            now = time.time()
            if entry.is_expired(now):
                del self._store[key]
                await self._notify_invalidation(key)
                return default
            return entry.value

    async def set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        expires_at = None if ttl_seconds is None else (time.time() + max(ttl_seconds, 0.0))
        async with self._lock:
            self._store[key] = _CacheEntry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            existed = key in self._store
            if existed:
                del self._store[key]
        if existed:
            await self._notify_invalidation(key)

    async def exists(self, key: str) -> bool:
        value = await self.get(key, default=None)
        return value is not None

    async def clear(self) -> None:
        async with self._lock:
            keys = list(self._store)
            self._store.clear()
        for key in keys:
            await self._notify_invalidation(key)

    async def _notify_invalidation(self, key: str) -> None:
        for hook in self._invalidation_hooks:
            result = hook(key)
            if asyncio.iscoroutine(result):
                await result

