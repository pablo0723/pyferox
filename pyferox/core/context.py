"""Execution context shared across transports."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(slots=True)
class ExecutionContext:
    request_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str | None = None
    correlation_id: str | None = None
    transport: str = "internal"
    current_user: object | None = None
    db_session: object | None = None
    services: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.correlation_id is None:
            self.correlation_id = self.trace_id or self.request_id

    def set_service(self, name: str, value: object) -> None:
        self.services[name] = value

    def get_service(self, name: str, default: object | None = None) -> object | None:
        return self.services.get(name, default)
