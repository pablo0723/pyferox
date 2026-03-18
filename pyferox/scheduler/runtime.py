"""Scheduler runtime for delayed and periodic execution."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import StrEnum
from heapq import heappop, heappush
from typing import Any, Awaitable, Callable

from pyferox.reliability import RetryClassifier, RetryPolicy, default_retry_classifier

TaskFn = Callable[[], Awaitable[Any] | Any]


@dataclass(slots=True)
class ScheduledTask:
    name: str
    fn: TaskFn
    run_at: float
    interval_seconds: float | None = None
    max_retries: int = 0
    attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ScheduleResultStatus(StrEnum):
    SUCCESS = "success"
    RETRIED = "retried"
    FAILED = "failed"


@dataclass(slots=True)
class ScheduleRunResult:
    task_name: str
    status: ScheduleResultStatus
    attempts: int
    error: str | None = None


class SchedulerRuntime:
    """In-process scheduler with delayed and interval tasks."""

    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        retry_classifier: RetryClassifier | None = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=2, base_delay_seconds=0.25)
        self.retry_classifier = retry_classifier or default_retry_classifier
        self._heap: list[tuple[float, int, ScheduledTask]] = []
        self._counter = 0
        self._stop_event = asyncio.Event()

    def schedule_interval(
        self,
        name: str,
        *,
        interval_seconds: float,
        fn: TaskFn,
        delay_seconds: float = 0.0,
        max_retries: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        task = ScheduledTask(
            name=name,
            fn=fn,
            run_at=time.time() + max(delay_seconds, 0.0),
            interval_seconds=interval_seconds,
            max_retries=max(0, max_retries),
            metadata=metadata or {},
        )
        self._push(task)

    def schedule_delayed(
        self,
        name: str,
        *,
        delay_seconds: float,
        fn: TaskFn,
        max_retries: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        task = ScheduledTask(
            name=name,
            fn=fn,
            run_at=time.time() + max(delay_seconds, 0.0),
            interval_seconds=None,
            max_retries=max(0, max_retries),
            metadata=metadata or {},
        )
        self._push(task)

    async def run_once(self, *, timeout: float | None = None) -> list[ScheduleRunResult]:
        if timeout is not None and timeout > 0:
            await asyncio.sleep(timeout)
        now = time.time()
        due: list[ScheduledTask] = []
        while self._heap and self._heap[0][0] <= now:
            _, _, task = heappop(self._heap)
            due.append(task)
        results: list[ScheduleRunResult] = []
        for task in due:
            results.append(await self._run_task(task))
        return results

    async def run_forever(self, *, poll_interval: float = 0.25) -> None:
        while not self._stop_event.is_set():
            await self.run_once()
            await asyncio.sleep(max(0.0, poll_interval))

    def stop(self) -> None:
        self._stop_event.set()

    async def _run_task(self, task: ScheduledTask) -> ScheduleRunResult:
        task.attempts += 1
        try:
            result = task.fn()
            if asyncio.iscoroutine(result):
                await result
            if task.interval_seconds is not None:
                task.run_at = time.time() + task.interval_seconds
                task.attempts = 0
                self._push(task)
            return ScheduleRunResult(task_name=task.name, status=ScheduleResultStatus.SUCCESS, attempts=task.attempts)
        except Exception as exc:
            decision = self.retry_classifier(exc)
            if task.attempts <= task.max_retries and self.retry_policy.should_retry(attempt=task.attempts, decision=decision):
                delay = self.retry_policy.next_delay_seconds(attempt=task.attempts)
                task.run_at = time.time() + delay
                self._push(task)
                return ScheduleRunResult(
                    task_name=task.name,
                    status=ScheduleResultStatus.RETRIED,
                    attempts=task.attempts,
                    error=str(exc),
                )
            if task.interval_seconds is not None:
                task.run_at = time.time() + task.interval_seconds
                task.attempts = 0
                self._push(task)
            return ScheduleRunResult(
                task_name=task.name,
                status=ScheduleResultStatus.FAILED,
                attempts=task.attempts,
                error=str(exc),
            )

    def _push(self, task: ScheduledTask) -> None:
        self._counter += 1
        heappush(self._heap, (task.run_at, self._counter, task))
