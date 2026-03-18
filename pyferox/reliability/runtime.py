"""Retry and idempotency primitives for distributed runtime behavior."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pyferox.core.errors import InfrastructureError


class RetryDisposition(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass(slots=True)
class RetryDecision:
    disposition: RetryDisposition
    reason: str = ""

    @property
    def retryable(self) -> bool:
        return self.disposition == RetryDisposition.TRANSIENT


class RetryClassifier(Protocol):
    def classify(self, exc: Exception) -> RetryDecision:
        ...


def default_retry_classifier(exc: Exception) -> RetryDecision:
    if isinstance(exc, (TimeoutError, ConnectionError, InfrastructureError, RuntimeError)):
        return RetryDecision(RetryDisposition.TRANSIENT, reason=type(exc).__name__)
    return RetryDecision(RetryDisposition.PERMANENT, reason=type(exc).__name__)


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    jitter_seconds: float = 0.0

    def should_retry(self, *, attempt: int, decision: RetryDecision) -> bool:
        return decision.retryable and attempt < max(1, self.max_attempts)

    def next_delay_seconds(self, *, attempt: int) -> float:
        power = max(0, attempt - 1)
        delay = self.base_delay_seconds * (self.backoff_multiplier**power)
        delay = min(delay, self.max_delay_seconds)
        if self.jitter_seconds > 0:
            delay += random.uniform(0.0, self.jitter_seconds)
        return max(0.0, delay)


class IdempotencyStore(Protocol):
    async def reserve(self, key: str, *, ttl_seconds: float | None = None) -> bool:
        ...

    async def complete(self, key: str, *, result: Any = None) -> None:
        ...

    async def fail(self, key: str, *, error: str | None = None) -> None:
        ...

    async def result(self, key: str) -> Any | None:
        ...

    async def status(self, key: str) -> str | None:
        ...


@dataclass(slots=True)
class _IdempotencyRecord:
    status: str
    expires_at: float | None
    result: Any = None
    error: str | None = None


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[str, _IdempotencyRecord] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, key: str, *, ttl_seconds: float | None = None) -> bool:
        async with self._lock:
            self._cleanup_expired()
            existing = self._records.get(key)
            if existing is not None:
                return False
            expires_at = None if ttl_seconds is None else time.time() + max(ttl_seconds, 0.0)
            self._records[key] = _IdempotencyRecord(status="reserved", expires_at=expires_at)
            return True

    async def complete(self, key: str, *, result: Any = None) -> None:
        async with self._lock:
            self._cleanup_expired()
            record = self._records.get(key)
            if record is None:
                self._records[key] = _IdempotencyRecord(status="completed", expires_at=None, result=result)
                return
            record.status = "completed"
            record.result = result
            record.error = None

    async def fail(self, key: str, *, error: str | None = None) -> None:
        async with self._lock:
            self._cleanup_expired()
            record = self._records.get(key)
            if record is None:
                self._records[key] = _IdempotencyRecord(status="failed", expires_at=None, error=error)
                return
            record.status = "failed"
            record.error = error

    async def result(self, key: str) -> Any | None:
        async with self._lock:
            self._cleanup_expired()
            record = self._records.get(key)
            if record is None:
                return None
            if record.status != "completed":
                return None
            return record.result

    async def status(self, key: str) -> str | None:
        async with self._lock:
            self._cleanup_expired()
            record = self._records.get(key)
            return None if record is None else record.status

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [key for key, value in self._records.items() if value.expires_at is not None and value.expires_at <= now]
        for key in expired:
            self._records.pop(key, None)
