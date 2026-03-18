from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pyferox import App, Event, Module, listen
from pyferox.events import DistributedEventBus, EventResultStatus, InMemoryEventBroker
from pyferox.reliability import RetryPolicy


@dataclass(slots=True)
class UserCreated(Event):
    user_id: int


def test_distributed_event_bus_publish_and_consume() -> None:
    seen: list[int] = []

    @listen(UserCreated)
    async def on_user_created(event: UserCreated) -> None:
        seen.append(event.user_id)

    app = App(modules=[Module(listeners=[on_user_created])])
    broker = InMemoryEventBroker()
    bus = DistributedEventBus(app, broker=broker)

    async def run() -> EventResultStatus | None:
        await bus.bind("users.created", UserCreated)
        await bus.publish(UserCreated(user_id=7), topic="users.created")
        result = await bus.run_once(timeout=0.1)
        return result.status if result is not None else None

    assert asyncio.run(run()) == EventResultStatus.SUCCESS
    assert seen == [7]


def test_distributed_event_bus_retries_failed_event() -> None:
    attempts = {"count": 0}

    @listen(UserCreated)
    async def flaky(_: UserCreated) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("temporary")

    app = App(modules=[Module(listeners=[flaky])])
    broker = InMemoryEventBroker()
    bus = DistributedEventBus(app, broker=broker, retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0))

    async def run() -> tuple[EventResultStatus | None, EventResultStatus | None]:
        await bus.bind("users.created", UserCreated)
        await bus.publish(UserCreated(user_id=1), topic="users.created", max_retries=1, backoff_seconds=0.0)
        first = await bus.run_once(timeout=0.1)
        await asyncio.sleep(0.01)
        second = await bus.run_once(timeout=0.1)
        return first.status if first else None, second.status if second else None

    first_status, second_status = asyncio.run(run())
    assert first_status == EventResultStatus.RETRIED
    assert second_status == EventResultStatus.SUCCESS
    assert attempts["count"] == 2
