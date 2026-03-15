"""Execution context shared across transports."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(slots=True)
class ExecutionContext:
    request_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str | None = None
    current_user: object | None = None
    db_session: object | None = None
    services: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
