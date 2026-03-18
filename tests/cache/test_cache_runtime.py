from __future__ import annotations

import asyncio

from pyferox.cache import InMemoryCache


def test_in_memory_cache_set_get_delete_exists() -> None:
    cache = InMemoryCache()

    async def run() -> None:
        assert await cache.get("x") is None
        await cache.set("x", 10)
        assert await cache.get("x") == 10
        assert await cache.exists("x") is True
        await cache.delete("x")
        assert await cache.exists("x") is False

    asyncio.run(run())


def test_in_memory_cache_ttl_expiration() -> None:
    cache = InMemoryCache()

    async def run() -> None:
        await cache.set("x", "ok", ttl_seconds=0.02)
        assert await cache.get("x") == "ok"
        await asyncio.sleep(0.03)
        assert await cache.get("x") is None

    asyncio.run(run())


def test_in_memory_cache_invalidation_hooks() -> None:
    cache = InMemoryCache()
    invalidated: list[str] = []

    async def hook(key: str) -> None:
        invalidated.append(key)

    cache.add_invalidation_hook(hook)

    async def run() -> None:
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.delete("a")
        await cache.clear()

    asyncio.run(run())
    assert invalidated == ["a", "b"]

