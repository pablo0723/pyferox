from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from pyferox import App, Module, handle
from pyferox.jobs.runtime import JobEnvelope, _idempotency_ttl
from pyferox.jobs import InMemoryJobQueue, Job, JobDispatcher, JobStatus, WorkerRuntime
from pyferox.reliability import InMemoryIdempotencyStore, RetryPolicy


@dataclass(slots=True)
class Ping(Job):
    value: str


def test_in_memory_job_queue_wait_paths_and_size() -> None:
    queue = InMemoryJobQueue()

    async def run() -> tuple[bool, bool, int]:
        assert await queue.dequeue(timeout=0.0) is None
        future = JobEnvelope(id="1", job=Ping(value="x"), run_at=time.time() + 0.01)
        await queue.enqueue(future)
        item = await queue.dequeue(timeout=0.05)

        async def wait_dequeue() -> JobEnvelope | None:
            return await queue.dequeue(timeout=None)

        task = asyncio.create_task(wait_dequeue())
        await asyncio.sleep(0.005)
        await queue.enqueue(JobEnvelope(id="2", job=Ping(value="y"), run_at=time.time()))
        item2 = await task
        return item is not None, item2 is not None, await queue.size()

    has_first, has_second, size = asyncio.run(run())
    assert has_first is True
    assert has_second is True
    assert size == 0


def test_job_dispatcher_cached_idempotency_and_fail_update_and_backoff_delay() -> None:
    attempts = {"count": 0}

    @handle(Ping)
    async def flaky(_: Ping) -> None:
        attempts["count"] += 1
        raise RuntimeError("boom")

    app = App(modules=[Module(handlers=[flaky])])
    store = InMemoryIdempotencyStore()
    dispatcher = JobDispatcher(
        app,
        idempotency_store=store,
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
    )

    async def run() -> tuple[JobStatus | None, JobStatus | None, str | None]:
        await store.complete("cached", result={"ok": True})
        await dispatcher.enqueue(Ping(value="x"), idempotency_key="cached")
        skipped = await dispatcher.run_once(timeout=0.1)

        await dispatcher.enqueue(Ping(value="x"), idempotency_key="k2", max_retries=1, backoff_seconds=0.01)
        retried = await dispatcher.run_once(timeout=0.1)
        failed_status = await store.status("k2")
        return skipped.status if skipped else None, retried.status if retried else None, failed_status

    skipped_status, retried_status, failed_status = asyncio.run(run())
    assert skipped_status == JobStatus.SKIPPED
    assert retried_status == JobStatus.RETRIED
    assert failed_status == "failed"


def test_worker_runtime_lifecycle_and_run_forever() -> None:
    seen: list[str] = []

    @handle(Ping)
    async def handle_ping(job: Ping) -> None:
        seen.append(job.value)

    app = App(modules=[Module(handlers=[handle_ping])])
    dispatcher = JobDispatcher(app)
    worker = WorkerRuntime(dispatcher)

    async def run() -> None:
        await worker.startup()
        await dispatcher.enqueue(Ping(value="ok"))
        task = asyncio.create_task(worker.run_forever(poll_interval=0.001))
        await asyncio.sleep(0.01)
        await worker.shutdown()
        await task

    asyncio.run(run())
    assert seen == ["ok"]


def test_idempotency_ttl_helper_invalid_value() -> None:
    assert _idempotency_ttl({"idempotency_ttl_seconds": "bad"}) is None


def test_job_queue_future_timeout_zero_returns_none() -> None:
    queue = InMemoryJobQueue()

    async def run() -> JobEnvelope | None:
        await queue.enqueue(JobEnvelope(id="future", job=Ping(value="x"), run_at=time.time() + 1.0))
        return await queue.dequeue(timeout=0.0)

    assert asyncio.run(run()) is None


def test_job_queue_waits_for_scheduled_item_without_timeout() -> None:
    queue = InMemoryJobQueue()

    async def run() -> JobEnvelope | None:
        await queue.enqueue(JobEnvelope(id="soon", job=Ping(value="x"), run_at=time.time() + 0.01))
        return await queue.dequeue(timeout=None)

    item = asyncio.run(run())
    assert item is not None
    assert item.id == "soon"
