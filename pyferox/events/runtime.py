"""Event bus abstractions for local and distributed runtime dispatch."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from pyferox.core import App
from pyferox.reliability import RetryPolicy
from pyferox.schema import parse_input, serialize_output


@dataclass(slots=True)
class EventEnvelope:
    id: str
    topic: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    max_retries: int = 3
    backoff_seconds: float = 0.5


class EventResultStatus(StrEnum):
    SUCCESS = "success"
    RETRIED = "retried"
    FAILED = "failed"


@dataclass(slots=True)
class EventDispatchResult:
    envelope_id: str
    status: EventResultStatus
    attempts: int
    error: str | None = None


class EventBroker(Protocol):
    async def publish(self, topic: str, envelope: EventEnvelope) -> None:
        ...

    async def subscribe(self, topic: str) -> asyncio.Queue[EventEnvelope]:
        ...


class InMemoryEventBroker:
    """Fan-out broker that copies events to subscriber queues by topic."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[EventEnvelope]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, envelope: EventEnvelope) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(topic, []))
        for queue in queues:
            await queue.put(envelope)

    async def subscribe(self, topic: str) -> asyncio.Queue[EventEnvelope]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        async with self._lock:
            self._subscribers[topic].append(queue)
        return queue


class LocalEventBus:
    def __init__(self, app: App) -> None:
        self.app = app

    async def publish(self, event: Any) -> None:
        await self.app.publish(event)


class DistributedEventBus:
    def __init__(
        self,
        app: App,
        *,
        broker: EventBroker,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.app = app
        self.broker = broker
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=3, base_delay_seconds=0.5)
        self._bindings: dict[str, type[Any]] = {}
        self._queues: dict[str, asyncio.Queue[EventEnvelope]] = {}

    async def bind(self, topic: str, event_type: type[Any]) -> None:
        if topic in self._bindings:
            raise ValueError(f"Topic already bound: {topic}")
        self._bindings[topic] = event_type
        self._queues[topic] = await self.broker.subscribe(topic)

    async def publish(
        self,
        event: Any,
        *,
        topic: str | None = None,
        metadata: dict[str, Any] | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> str:
        topic_name = topic or type(event).__name__
        payload = serialize_output(event)
        if not isinstance(payload, dict):
            payload = {"value": payload}
        envelope = EventEnvelope(
            id=str(uuid4()),
            topic=topic_name,
            payload=payload,
            metadata=metadata or {},
            max_retries=max(0, max_retries),
            backoff_seconds=max(0.0, backoff_seconds),
        )
        await self.broker.publish(topic_name, envelope)
        return envelope.id

    async def run_once(self, *, timeout: float | None = None) -> EventDispatchResult | None:
        if not self._queues:
            return None

        queue_tasks = [asyncio.create_task(queue.get()) for queue in self._queues.values()]
        done: set[asyncio.Task[EventEnvelope]]
        pending: set[asyncio.Task[EventEnvelope]]
        done, pending = await asyncio.wait(queue_tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()
        if not done:
            await asyncio.gather(*pending, return_exceptions=True)
            return None

        envelope = next(iter(done)).result()
        await asyncio.gather(*pending, return_exceptions=True)
        return await self._handle_envelope(envelope)

    async def _handle_envelope(self, envelope: EventEnvelope) -> EventDispatchResult:
        event_type = self._bindings.get(envelope.topic)
        if event_type is None:
            return EventDispatchResult(
                envelope_id=envelope.id,
                status=EventResultStatus.FAILED,
                attempts=envelope.attempts,
                error=f"No binding for topic: {envelope.topic}",
            )

        envelope.attempts += 1
        try:
            event = parse_input(event_type, envelope.payload)
            await self.app.publish(event)
            return EventDispatchResult(
                envelope_id=envelope.id,
                status=EventResultStatus.SUCCESS,
                attempts=envelope.attempts,
            )
        except Exception as exc:
            if envelope.attempts <= envelope.max_retries:
                delay = envelope.backoff_seconds * (2 ** max(0, envelope.attempts - 1))
                delay = max(delay, self.retry_policy.next_delay_seconds(attempt=envelope.attempts))
                asyncio.create_task(self._republish_after_delay(envelope, delay_seconds=delay))
                return EventDispatchResult(
                    envelope_id=envelope.id,
                    status=EventResultStatus.RETRIED,
                    attempts=envelope.attempts,
                    error=str(exc),
                )
            return EventDispatchResult(
                envelope_id=envelope.id,
                status=EventResultStatus.FAILED,
                attempts=envelope.attempts,
                error=str(exc),
            )

    async def _republish_after_delay(self, envelope: EventEnvelope, *, delay_seconds: float) -> None:
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        await self.broker.publish(envelope.topic, envelope)


def event_metadata(*, source: str, event_id: str | None = None) -> dict[str, Any]:
    return {
        "source": source,
        "event_id": event_id or str(uuid4()),
        "published_at": time.time(),
    }
