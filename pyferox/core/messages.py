"""Message markers used by command/query/event handlers."""

from dataclasses import dataclass


@dataclass(slots=True)
class Command:
    """Base type for write-side operations."""


@dataclass(slots=True)
class Query:
    """Base type for read-side operations."""


@dataclass(slots=True)
class Event:
    """Base type for domain/integration events."""

