from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox import App, Event, Module, listen
from pyferox.events import (
    DistributedEventBus,
    EventDispatchResult,
    EventEnvelope,
    EventResultStatus,
    InMemoryEventBroker,
    LocalEventBus,
    event_metadata,
)
from pyferox.reliability import RetryPolicy


@dataclass(slots=True)
class Ping(Event):
    value: int


def test_local_event_bus_publish_and_event_metadata_helper() -> None:
    seen: list[int] = []

    @listen(Ping)
    async def on_ping(event: Ping) -> None:
        seen.append(event.value)

    app = App(modules=[Module(listeners=[on_ping])])
    bus = LocalEventBus(app)
    asyncio.run(bus.publish(Ping(value=3)))
    assert seen == [3]

    meta = event_metadata(source="svc")
    assert meta["source"] == "svc"
    assert "event_id" in meta
    assert "published_at" in meta


def test_distributed_event_bus_duplicate_bind_and_no_queue_timeout() -> None:
    app = App()
    broker = InMemoryEventBroker()
    bus = DistributedEventBus(app, broker=broker)

    async def run() -> None:
        await bus.bind("t", Ping)
        with pytest.raises(ValueError):
            await bus.bind("t", Ping)
        assert await bus.run_once(timeout=0.001) is None

    asyncio.run(run())


def test_distributed_event_bus_run_once_without_bindings_returns_none() -> None:
    bus = DistributedEventBus(App(), broker=InMemoryEventBroker())
    assert asyncio.run(bus.run_once(timeout=0.001)) is None


def test_distributed_event_bus_non_dict_payload_and_missing_binding_paths() -> None:
    app = App()
    broker = InMemoryEventBroker()
    bus = DistributedEventBus(app, broker=broker)

    async def run() -> tuple[str, EventResultStatus]:
        event_id = await bus.publish(5, topic="raw")  # type: ignore[arg-type]
        assert isinstance(event_id, str)
        envelope = EventEnvelope(id="1", topic="missing", payload={"x": 1})
        result = await bus._handle_envelope(envelope)
        return event_id, result.status

    event_id, status = asyncio.run(run())
    assert event_id
    assert status == EventResultStatus.FAILED


def test_distributed_event_bus_failed_after_retry_exhaustion_and_republish_delay() -> None:
    @listen(Ping)
    async def always_fail(_: Ping) -> None:
        raise RuntimeError("boom")

    app = App(modules=[Module(listeners=[always_fail])])
    broker = InMemoryEventBroker()
    bus = DistributedEventBus(app, broker=broker, retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0.0))

    async def run() -> tuple[EventResultStatus | None, EventResultStatus | None]:
        await bus.bind("ping", Ping)
        await bus.publish(Ping(value=1), topic="ping", max_retries=1, backoff_seconds=0.001)
        first = await bus.run_once(timeout=0.05)
        await asyncio.sleep(0.01)
        second = await bus.run_once(timeout=0.05)
        return first.status if first else None, second.status if second else None

    first, second = asyncio.run(run())
    assert first == EventResultStatus.RETRIED
    assert second == EventResultStatus.FAILED


def test_distributed_event_bus_republish_after_delay_branch(monkeypatch) -> None:
    app = App()
    broker = InMemoryEventBroker()
    bus = DistributedEventBus(app, broker=broker)
    envelope = EventEnvelope(id="e1", topic="t1", payload={})
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("pyferox.events.runtime.asyncio.sleep", fake_sleep)

    async def run() -> EventDispatchResult | None:
        await bus.bind("t1", Ping)
        await bus._republish_after_delay(envelope, delay_seconds=0.01)
        return await bus.run_once(timeout=0.05)

    result = asyncio.run(run())
    assert slept and slept[0] == 0.01
    assert result is not None
