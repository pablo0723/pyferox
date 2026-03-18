"""Single-node jobs runtime with delayed execution and retries."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum
from heapq import heappop, heappush
from typing import Any, Protocol
from uuid import uuid4

from pyferox.core import App, Message


class Job(Message):
    """Base contract for background jobs."""


@dataclass(slots=True)
class JobEnvelope:
    id: str
    job: Job
    run_at: float
    attempts: int = 0
    max_retries: int = 3
    backoff_seconds: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class JobStatus(StrEnum):
    SUCCESS = "success"
    RETRIED = "retried"
    FAILED = "failed"


@dataclass(slots=True)
class JobExecutionResult:
    envelope_id: str
    status: JobStatus
    attempts: int
    error: str | None = None


class JobQueue(Protocol):
    async def enqueue(self, envelope: JobEnvelope) -> None:
        ...

    async def dequeue(self, *, timeout: float | None = None) -> JobEnvelope | None:
        ...

    async def requeue(self, envelope: JobEnvelope, *, delay_seconds: float) -> None:
        ...

    async def size(self) -> int:
        ...


class InMemoryJobQueue:
    """Priority queue backed by asyncio condition and run-at scheduling."""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, JobEnvelope]] = []
        self._condition = asyncio.Condition()
        self._counter = 0

    async def enqueue(self, envelope: JobEnvelope) -> None:
        async with self._condition:
            self._counter += 1
            heappush(self._heap, (envelope.run_at, self._counter, envelope))
            self._condition.notify()

    async def dequeue(self, *, timeout: float | None = None) -> JobEnvelope | None:
        start = time.monotonic()
        async with self._condition:
            while True:
                now = time.time()
                if self._heap:
                    run_at, _, envelope = self._heap[0]
                    if run_at <= now:
                        heappop(self._heap)
                        return envelope
                    wait_for = run_at - now
                    if timeout is not None:
                        elapsed = time.monotonic() - start
                        remaining = timeout - elapsed
                        if remaining <= 0:
                            return None
                        wait_for = min(wait_for, remaining)
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=wait_for)
                    except TimeoutError:
                        if timeout is not None:
                            elapsed = time.monotonic() - start
                            if elapsed >= timeout:
                                return None
                    continue

                if timeout is None:
                    await self._condition.wait()
                    continue

                elapsed = time.monotonic() - start
                remaining = timeout - elapsed
                if remaining <= 0:
                    return None
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    return None

    async def requeue(self, envelope: JobEnvelope, *, delay_seconds: float) -> None:
        envelope.run_at = time.time() + max(delay_seconds, 0.0)
        await self.enqueue(envelope)

    async def size(self) -> int:
        async with self._condition:
            return len(self._heap)


class JobDispatcher:
    """Dispatches queued jobs via app execution pipeline."""

    def __init__(self, app: App, *, queue: JobQueue | None = None) -> None:
        self.app = app
        self.queue = queue or InMemoryJobQueue()

    async def enqueue(
        self,
        job: Job,
        *,
        delay_seconds: float = 0.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        envelope = JobEnvelope(
            id=str(uuid4()),
            job=job,
            run_at=time.time() + max(delay_seconds, 0.0),
            max_retries=max(0, max_retries),
            backoff_seconds=max(backoff_seconds, 0.0),
            metadata=metadata or {},
        )
        await self.queue.enqueue(envelope)
        return envelope.id

    async def run_once(self, *, timeout: float | None = None) -> JobExecutionResult | None:
        envelope = await self.queue.dequeue(timeout=timeout)
        if envelope is None:
            return None
        envelope.attempts += 1
        try:
            await self.app.execute(envelope.job)
            return JobExecutionResult(
                envelope_id=envelope.id,
                status=JobStatus.SUCCESS,
                attempts=envelope.attempts,
            )
        except Exception as exc:
            if envelope.attempts <= envelope.max_retries:
                delay = envelope.backoff_seconds * (2 ** (envelope.attempts - 1))
                await self.queue.requeue(envelope, delay_seconds=delay)
                return JobExecutionResult(
                    envelope_id=envelope.id,
                    status=JobStatus.RETRIED,
                    attempts=envelope.attempts,
                    error=str(exc),
                )
            return JobExecutionResult(
                envelope_id=envelope.id,
                status=JobStatus.FAILED,
                attempts=envelope.attempts,
                error=str(exc),
            )


class LocalJobWorker:
    """Runs queued jobs in a local async loop."""

    def __init__(self, dispatcher: JobDispatcher) -> None:
        self.dispatcher = dispatcher
        self._stop_event = asyncio.Event()

    async def run(self, *, idle_timeout: float = 0.25) -> None:
        while not self._stop_event.is_set():
            await self.dispatcher.run_once(timeout=idle_timeout)

    async def run_until_idle(self, *, idle_rounds: int = 1, timeout: float = 0.05) -> None:
        rounds = 0
        while rounds < idle_rounds:
            result = await self.dispatcher.run_once(timeout=timeout)
            if result is None:
                rounds += 1
            else:
                rounds = 0

    def stop(self) -> None:
        self._stop_event.set()
