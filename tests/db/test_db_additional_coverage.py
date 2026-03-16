from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import pyferox.db as db_package
from pyferox.core import ExecutionContext, Scope
from pyferox.db import DBSessionMiddleware, Repository, SQLAlchemySettings, UnitOfWork, sqlalchemy_module


def test_db_package_exports() -> None:
    assert db_package.Repository is Repository
    assert db_package.UnitOfWork is UnitOfWork


def test_repository_keeps_session_reference() -> None:
    session = object()
    repo = Repository(session=session)  # type: ignore[arg-type]
    assert repo.session is session


def test_unit_of_work_requires_active_session_for_commit_and_rollback() -> None:
    uow = UnitOfWork(lambda: None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        asyncio.run(uow.commit())
    with pytest.raises(RuntimeError):
        asyncio.run(uow.rollback())


def test_unit_of_work_exit_without_session_is_noop() -> None:
    uow = UnitOfWork(lambda: None)  # type: ignore[arg-type]
    asyncio.run(uow.__aexit__(None, None, None))


def test_sqlalchemy_module_respects_custom_scope() -> None:
    module = sqlalchemy_module(SQLAlchemySettings(url="sqlite+aiosqlite:///:memory:"), uow_scope=Scope.JOB)
    session_provider = next(entry for entry in module.providers if entry.key is AsyncSession)
    assert session_provider.scope == Scope.JOB


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_db_session_middleware_cleans_up_on_error() -> None:
    session = FakeSession()
    middleware = DBSessionMiddleware(lambda: session)  # type: ignore[arg-type]
    context = ExecutionContext()

    async def call_next(message: object) -> None:
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        asyncio.run(middleware(context, object(), call_next))
    assert session.closed is True
    assert context.db_session is None
    assert "db_session" not in context.services


class FakeTransaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUOWSession:
    def __init__(self) -> None:
        self.closed = False
        self.committed = False
        self.rolled_back = False
        self.transaction = FakeTransaction()

    async def begin(self) -> FakeTransaction:
        return self.transaction

    async def close(self) -> None:
        self.closed = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def test_unit_of_work_commit_and_rollback_paths() -> None:
    session = FakeUOWSession()
    uow = UnitOfWork(lambda: session)  # type: ignore[arg-type]

    async def run_commit() -> None:
        async with uow:
            assert uow.session is session
        assert session.transaction.committed is True
        assert session.closed is True

    asyncio.run(run_commit())

    session2 = FakeUOWSession()
    uow2 = UnitOfWork(lambda: session2)  # type: ignore[arg-type]

    async def run_rollback() -> None:
        try:
            async with uow2:
                raise ValueError("boom")
        except ValueError:
            pass
        assert session2.transaction.rolled_back is True
        assert session2.closed is True

    asyncio.run(run_rollback())


def test_unit_of_work_direct_commit_and_rollback_when_active() -> None:
    session = FakeUOWSession()
    uow = UnitOfWork(lambda: session)  # type: ignore[arg-type]
    uow.session = session
    asyncio.run(uow.commit())
    asyncio.run(uow.rollback())
    assert session.committed is True
    assert session.rolled_back is True


def test_sqlalchemy_module_shutdown_hook_runs() -> None:
    module = sqlalchemy_module(SQLAlchemySettings(url="sqlite+aiosqlite:///:memory:"))
    shutdown = module.on_shutdown[0]
    asyncio.run(shutdown())
