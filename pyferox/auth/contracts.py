"""Core auth interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class Identity:
    subject: str
    email: str | None = None


@dataclass(slots=True)
class Principal:
    identity: Identity
    roles: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=set)


class AuthBackend(Protocol):
    async def authenticate(self, token: str | None) -> Principal | None:
        ...


class PermissionChecker(Protocol):
    async def allowed(self, principal: Principal | None, permission: str) -> bool:
        ...

