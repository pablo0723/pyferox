"""SQLAlchemy async integration for PyFerOx."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from pyferox.core.context import ExecutionContext
from pyferox.core.di import Scope, provider, singleton
from pyferox.core.middleware import NextCallable
from pyferox.core.module import Module


@dataclass(slots=True)
class SQLAlchemySettings:
    url: str
    echo: bool = False


class UnitOfWork:
    """Async transaction boundary for handlers."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._transaction: Any = None

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self._session_factory()
        self._transaction = await self.session.begin()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.session is None:
            return
        try:
            if exc is None:
                await self._transaction.commit()
            else:
                await self._transaction.rollback()
        finally:
            await self.session.close()
            self.session = None
            self._transaction = None

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active")
        await self.session.commit()

    async def rollback(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWork session is not active")
        await self.session.rollback()


class DBSessionMiddleware:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(self, context: ExecutionContext, message: Any, call_next: NextCallable) -> Any:
        session = self._session_factory()
        context.db_session = session
        context.set_service("db_session", session)
        try:
            return await call_next(message)
        finally:
            await session.close()
            context.services.pop("db_session", None)
            if context.db_session is session:
                context.db_session = None


def sqlalchemy_module(
    settings: SQLAlchemySettings,
    *,
    uow_scope: Scope = Scope.REQUEST,
) -> Module:
    """Build a module that provides AsyncEngine and request-scoped UnitOfWork."""
    engine = create_async_engine(settings.url, echo=settings.echo)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def on_shutdown() -> None:
        await engine.dispose()

    return Module(
        providers=[
            singleton(engine, key=AsyncEngine),
            singleton(session_factory, key=async_sessionmaker),
            provider(AsyncSession, lambda: session_factory(), scope=uow_scope),
            provider(UnitOfWork, lambda: UnitOfWork(session_factory), scope=uow_scope),
        ],
        on_shutdown=[on_shutdown],
    )
