"""Session utilities and an in-memory auth backend."""

from __future__ import annotations

from typing import Any

from pyferox.auth.contracts import AuthBackend, Identity, Principal, Session, SessionStore


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            self._sessions.pop(session_id, None)
            return None
        return session

    async def set(self, session: Session) -> None:
        self._sessions[session.session_id] = session

    async def revoke(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


class SessionAuthBackend(AuthBackend):
    """Auth backend resolving principals from a session store."""

    def __init__(
        self,
        store: SessionStore,
        *,
        subject_permissions: dict[str, set[str]] | None = None,
        subject_roles: dict[str, set[str]] | None = None,
    ) -> None:
        self._store = store
        self._subject_permissions = subject_permissions or {}
        self._subject_roles = subject_roles or {}

    async def authenticate(self, token: str | None) -> Principal | None:
        if token is None:
            return None
        session = await self._store.get(token)
        if session is None:
            return None
        return Principal(
            identity=Identity(subject=session.subject, email=_coerce_email(session.data)),
            roles=set(self._subject_roles.get(session.subject, set())),
            permissions=set(self._subject_permissions.get(session.subject, set())),
        )


def _coerce_email(data: dict[str, Any]) -> str | None:
    raw = data.get("email")
    return raw if isinstance(raw, str) else None

