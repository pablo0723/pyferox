from __future__ import annotations

import asyncio

from pyferox.core.errors import InfrastructureError
from pyferox.reliability import (
    InMemoryIdempotencyStore,
    RetryDisposition,
    RetryPolicy,
    default_retry_classifier,
)


def test_default_retry_classifier_and_policy() -> None:
    transient = default_retry_classifier(InfrastructureError("db"))
    permanent = default_retry_classifier(ValueError("bad"))
    assert transient.disposition == RetryDisposition.TRANSIENT
    assert permanent.disposition == RetryDisposition.PERMANENT

    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.01, jitter_seconds=0.0)
    assert policy.should_retry(attempt=1, decision=transient) is True
    assert policy.should_retry(attempt=3, decision=transient) is False
    assert policy.should_retry(attempt=1, decision=permanent) is False
    assert policy.next_delay_seconds(attempt=2) >= 0.01


def test_in_memory_idempotency_store_flow() -> None:
    store = InMemoryIdempotencyStore()

    async def run() -> tuple[bool, str | None, int | None, str | None]:
        first = await store.reserve("k1")
        second = await store.reserve("k1")
        await store.complete("k1", result=7)
        status = await store.status("k1")
        result = await store.result("k1")
        await store.fail("k1", error="x")
        failed_status = await store.status("k1")
        return first, status, result, failed_status

    first, status, result, failed_status = asyncio.run(run())
    assert first is True
    assert status == "completed"
    assert result == 7
    assert failed_status == "failed"


def test_in_memory_idempotency_store_ttl_expiry() -> None:
    store = InMemoryIdempotencyStore()

    async def run() -> bool:
        await store.reserve("k2", ttl_seconds=0.01)
        await asyncio.sleep(0.02)
        return await store.reserve("k2")

    assert asyncio.run(run()) is True
