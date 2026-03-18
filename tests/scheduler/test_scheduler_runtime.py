from __future__ import annotations

import asyncio

from pyferox.reliability import RetryPolicy
from pyferox.scheduler import ScheduleResultStatus, SchedulerRuntime


def test_scheduler_delayed_task_runs() -> None:
    seen: list[str] = []
    scheduler = SchedulerRuntime()
    scheduler.schedule_delayed("once", delay_seconds=0.01, fn=lambda: seen.append("ok"))

    async def run() -> int:
        await asyncio.sleep(0.02)
        results = await scheduler.run_once()
        return len(results)

    assert asyncio.run(run()) == 1
    assert seen == ["ok"]


def test_scheduler_interval_task_reschedules() -> None:
    seen: list[int] = []
    scheduler = SchedulerRuntime()
    scheduler.schedule_interval("tick", interval_seconds=0.01, fn=lambda: seen.append(1))

    async def run() -> list[ScheduleResultStatus]:
        first = await scheduler.run_once()
        await asyncio.sleep(0.02)
        second = await scheduler.run_once()
        return [first[0].status, second[0].status]

    statuses = asyncio.run(run())
    assert statuses == [ScheduleResultStatus.SUCCESS, ScheduleResultStatus.SUCCESS]
    assert len(seen) >= 2


def test_scheduler_retry_path() -> None:
    attempts = {"count": 0}
    scheduler = SchedulerRuntime(retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0))

    def flaky() -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("temporary")

    scheduler.schedule_delayed("flaky", delay_seconds=0.0, fn=flaky, max_retries=1)

    async def run() -> tuple[ScheduleResultStatus | None, ScheduleResultStatus | None]:
        first = await scheduler.run_once()
        await asyncio.sleep(0.01)
        second = await scheduler.run_once()
        return first[0].status if first else None, second[0].status if second else None

    first, second = asyncio.run(run())
    assert first == ScheduleResultStatus.RETRIED
    assert second == ScheduleResultStatus.SUCCESS
    assert attempts["count"] == 2
