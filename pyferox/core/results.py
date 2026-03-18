"""Transport-friendly result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from collections.abc import AsyncIterator, Iterator
from typing import Any


@dataclass(slots=True)
class Success:
    data: Any
    message: str | None = None


@dataclass(slots=True)
class Paginated:
    items: list[Any]
    total: int
    page: int
    page_size: int


@dataclass(slots=True)
class Empty:
    message: str | None = None


@dataclass(slots=True)
class Streamed:
    chunks: Iterator[Any] | AsyncIterator[Any]
    content_type: str = "application/octet-stream"


@dataclass(slots=True)
class Response:
    data: Any
    status_code: int = 200
    headers: dict[str, str] | None = None


def to_payload(value: Any) -> Any:
    if isinstance(value, (Success, Paginated, Empty)):
        return asdict(value)
    if isinstance(value, Streamed):
        return value
    if isinstance(value, Response):
        return value
    if is_dataclass(value):
        return asdict(value)
    return value
