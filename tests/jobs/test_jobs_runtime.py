from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pyferox import App, Module, handle
from pyferox.jobs import Job, JobDispatcher, JobStatus, LocalJobWorker, create_worker_runtime
from pyferox.reliability import InMemoryIdempotencyStore


@dataclass(slots=True)
class SendEmail(Job):
    address: str


def test_job_dispatcher_executes_job() -> None:
    seen: list[str] = []

    @handle(SendEmail)
    async def send_email(job: SendEmail) -> None:
        seen.append(job.address)

    app = App(modules=[Module(handlers=[send_email])])
    dispatcher = JobDispatcher(app)
    worker = LocalJobWorker(dispatcher)

    async def run() -> None:
        await dispatcher.enqueue(SendEmail(address="a@example.com"))
        await worker.run_until_idle()

    asyncio.run(run())
    assert seen == ["a@example.com"]


def test_job_dispatcher_retries_and_then_succeeds() -> None:
    attempts = {"count": 0}

    @handle(SendEmail)
    async def flaky(_: SendEmail) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary")

    app = App(modules=[Module(handlers=[flaky])])
    dispatcher = JobDispatcher(app)

    async def run() -> tuple[JobStatus | None, JobStatus | None]:
        await dispatcher.enqueue(SendEmail(address="x"), max_retries=2, backoff_seconds=0.0)
        first = await dispatcher.run_once(timeout=0.1)
        second = await dispatcher.run_once(timeout=0.1)
        return first.status if first else None, second.status if second else None

    first_status, second_status = asyncio.run(run())
    assert first_status == JobStatus.RETRIED
    assert second_status == JobStatus.SUCCESS
    assert attempts["count"] == 2


def test_job_dispatcher_marks_failed_after_max_retries() -> None:
    @handle(SendEmail)
    async def always_fail(_: SendEmail) -> None:
        raise RuntimeError("boom")

    app = App(modules=[Module(handlers=[always_fail])])
    dispatcher = JobDispatcher(app)

    async def run() -> JobStatus | None:
        await dispatcher.enqueue(SendEmail(address="x"), max_retries=1, backoff_seconds=0.0)
        first = await dispatcher.run_once(timeout=0.1)
        assert first is not None
        second = await dispatcher.run_once(timeout=0.1)
        return second.status if second else None

    assert asyncio.run(run()) == JobStatus.FAILED


def test_job_dispatcher_delay_support() -> None:
    seen: list[str] = []

    @handle(SendEmail)
    async def send_email(job: SendEmail) -> None:
        seen.append(job.address)

    app = App(modules=[Module(handlers=[send_email])])
    dispatcher = JobDispatcher(app)

    async def run() -> tuple[bool, bool]:
        await dispatcher.enqueue(SendEmail(address="later@example.com"), delay_seconds=0.03)
        first = await dispatcher.run_once(timeout=0.005)
        await asyncio.sleep(0.04)
        second = await dispatcher.run_once(timeout=0.05)
        return first is None, second is not None

    empty_first, got_second = asyncio.run(run())
    assert empty_first is True
    assert got_second is True
    assert seen == ["later@example.com"]


def test_job_dispatcher_idempotency_skips_duplicate_job() -> None:
    seen: list[str] = []

    @handle(SendEmail)
    async def send_email(job: SendEmail) -> None:
        seen.append(job.address)

    app = App(modules=[Module(handlers=[send_email])])
    dispatcher = JobDispatcher(app, idempotency_store=InMemoryIdempotencyStore())

    async def run() -> tuple[JobStatus | None, JobStatus | None]:
        await dispatcher.enqueue(SendEmail(address="x@example.com"), idempotency_key="job-1")
        await dispatcher.enqueue(SendEmail(address="x@example.com"), idempotency_key="job-1")
        first = await dispatcher.run_once(timeout=0.1)
        second = await dispatcher.run_once(timeout=0.1)
        return first.status if first else None, second.status if second else None

    first_status, second_status = asyncio.run(run())
    assert first_status == JobStatus.SUCCESS
    assert second_status == JobStatus.SKIPPED
    assert seen == ["x@example.com"]


def test_create_worker_runtime_bootstrap_helper() -> None:
    seen: list[str] = []

    @handle(SendEmail)
    async def send_email(job: SendEmail) -> None:
        seen.append(job.address)

    app = App(modules=[Module(handlers=[send_email])])
    worker = create_worker_runtime(app)

    async def run() -> None:
        await worker.dispatcher.enqueue(SendEmail(address="worker@example.com"))
        await worker.run_until_idle()

    asyncio.run(run())
    assert seen == ["worker@example.com"]
