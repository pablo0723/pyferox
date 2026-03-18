from __future__ import annotations

import asyncio

from pyferox.reliability import InMemoryIdempotencyStore, RetryDisposition, RetryPolicy


def test_retry_policy_jitter_branch(monkeypatch) -> None:
    monkeypatch.setattr("pyferox.reliability.runtime.random.uniform", lambda a, b: 0.5)
    policy = RetryPolicy(base_delay_seconds=1.0, jitter_seconds=1.0)
    assert policy.next_delay_seconds(attempt=1) == 1.5


def test_idempotency_store_missing_record_complete_fail_and_pending_result() -> None:
    store = InMemoryIdempotencyStore()

    async def run() -> tuple[int | None, str | None, str | None]:
        await store.complete("new", result=11)
        completed = await store.result("new")

        await store.fail("failed-key", error="boom")
        failed = await store.status("failed-key")

        await store.reserve("pending")
        pending_result = await store.result("pending")
        return completed, failed, "none" if pending_result is None else "set"

    completed, failed, pending_flag = asyncio.run(run())
    assert completed == 11
    assert failed == "failed"
    assert pending_flag == "none"


def test_retry_policy_should_retry_limits() -> None:
    policy = RetryPolicy(max_attempts=1)
    decision = type("D", (), {"retryable": True})()
    assert policy.should_retry(attempt=1, decision=decision) is False

    permanent = type("P", (), {"retryable": False, "disposition": RetryDisposition.PERMANENT})()
    assert policy.should_retry(attempt=0, decision=permanent) is False
