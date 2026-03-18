"""Core auth interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(slots=True)
class Identity:
    subject: str
    email: str | None = None


@dataclass(slots=True)
class Principal:
    identity: Identity
    roles: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=set)


@dataclass(slots=True)
class AccessToken:
    token: str
    subject: str
    expires_at: datetime | None = None
    scopes: set[str] = field(default_factory=set)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or datetime.now(tz=timezone.utc)
        return self.expires_at <= current


@dataclass(slots=True)
class Session:
    session_id: str
    subject: str
    expires_at: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or datetime.now(tz=timezone.utc)
        return self.expires_at <= current


class AuthBackend(Protocol):
    async def authenticate(self, token: str | None) -> Principal | None:
        ...


class PermissionChecker(Protocol):
    async def allowed(self, principal: Principal | None, permission: str) -> bool:
        ...


class SessionStore(Protocol):
    async def get(self, session_id: str) -> Session | None:
        ...

    async def set(self, session: Session) -> None:
        ...

    async def revoke(self, session_id: str) -> None:
        ...


def requires(permission: str):
    """Declare handler-level permission requirement."""

    def decorator(fn: Any) -> Any:
        setattr(fn, "__pyferox_permission__", permission)
        return fn

    return decorator
