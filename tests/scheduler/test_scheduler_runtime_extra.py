from __future__ import annotations

import asyncio

import pytest

from pyferox.reliability import RetryPolicy
from pyferox.scheduler import ScheduleResultStatus, SchedulerRuntime


def test_scheduler_invalid_interval_raises() -> None:
    scheduler = SchedulerRuntime()
    with pytest.raises(ValueError):
        scheduler.schedule_interval("bad", interval_seconds=0, fn=lambda: None)


def test_scheduler_run_once_timeout_branch_and_async_task() -> None:
    seen: list[str] = []
    scheduler = SchedulerRuntime()

    async def mark() -> None:
        seen.append("x")

    scheduler.schedule_delayed("async", delay_seconds=0.0, fn=mark)

    async def run() -> tuple[int, int]:
        first = await scheduler.run_once(timeout=0.001)
        second = await scheduler.run_once(timeout=0.001)
        return len(first), len(second)

    first_len, second_len = asyncio.run(run())
    assert first_len == 1
    assert second_len == 0
    assert seen == ["x"]


def test_scheduler_run_forever_stop_and_interval_failure_reschedule() -> None:
    scheduler = SchedulerRuntime(retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0.0))
    calls = {"count": 0}

    def fail_interval() -> None:
        calls["count"] += 1
        if calls["count"] >= 2:
            scheduler.stop()
        raise ValueError("x")

    scheduler.schedule_interval("f", interval_seconds=0.0_1, fn=fail_interval, max_retries=0)

    async def run() -> list[ScheduleResultStatus]:
        task = asyncio.create_task(scheduler.run_forever(poll_interval=0.0))
        await asyncio.sleep(0.01)
        await task
        first = await scheduler.run_once()
        return [item.status for item in first]

    statuses = asyncio.run(run())
    assert calls["count"] >= 1
    assert all(status in {ScheduleResultStatus.FAILED, ScheduleResultStatus.SUCCESS} for status in statuses)


def test_scheduler_failed_delayed_task_is_not_rescheduled_without_interval() -> None:
    scheduler = SchedulerRuntime(retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0.0))

    def fail_once() -> None:
        raise RuntimeError("boom")

    scheduler.schedule_delayed("fail", delay_seconds=0.0, fn=fail_once, max_retries=0)

    async def run() -> tuple[list[ScheduleResultStatus], list[object]]:
        first = await scheduler.run_once(timeout=0.05)
        second = await scheduler.run_once(timeout=0.001)
        return [item.status for item in first], second

    first_statuses, second = asyncio.run(run())
    assert first_statuses == [ScheduleResultStatus.FAILED]
    assert second == []
