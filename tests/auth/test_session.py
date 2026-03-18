from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from pyferox.auth import InMemorySessionStore, Session, SessionAuthBackend


def test_in_memory_session_store_and_backend() -> None:
    store = InMemorySessionStore()
    backend = SessionAuthBackend(
        store,
        subject_permissions={"user-1": {"users:read"}},
        subject_roles={"user-1": {"member"}},
    )

    async def run() -> None:
        session = Session(
            session_id="s1",
            subject="user-1",
            data={"email": "user@example.com"},
        )
        await store.set(session)
        principal = await backend.authenticate("s1")
        assert principal is not None
        assert principal.identity.subject == "user-1"
        assert principal.identity.email == "user@example.com"
        assert "users:read" in principal.permissions
        assert "member" in principal.roles

        await store.revoke("s1")
        assert await backend.authenticate("s1") is None

    asyncio.run(run())


def test_session_store_expired_session_is_not_returned() -> None:
    store = InMemorySessionStore()
    expired = Session(
        session_id="expired",
        subject="user-2",
        expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
    )

    async def run() -> None:
        await store.set(expired)
        loaded = await store.get("expired")
        assert loaded is None

    asyncio.run(run())

