from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

from sqlalchemy import Integer, String, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pyferox import App, Command, Module, Query, handle
from pyferox.core import ExecutionContext
from pyferox.db import DBSessionMiddleware, SQLAlchemySettings, UnitOfWork, sqlalchemy_module


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))


@dataclass(slots=True)
class CreateUser(Command):
    email: str
    name: str


@dataclass(slots=True)
class GetUser(Query):
    user_id: int


@handle(CreateUser)
async def create_user(cmd: CreateUser, uow: UnitOfWork) -> int:
    async with uow:
        assert uow.session is not None
        row = UserRow(email=cmd.email, name=cmd.name)
        uow.session.add(row)
        await uow.session.flush()
        return int(row.id)


@handle(GetUser)
async def get_user(query: GetUser, uow: UnitOfWork) -> dict[str, str]:
    async with uow:
        assert uow.session is not None
        result = await uow.session.execute(select(UserRow).where(UserRow.id == query.user_id))
        row = result.scalar_one()
        return {"email": row.email, "name": row.name}


def test_sqlalchemy_module_with_unit_of_work() -> None:
    db_module = sqlalchemy_module(SQLAlchemySettings(url="sqlite+aiosqlite:///:memory:"))
    app = App(modules=[db_module, Module(handlers=[create_user, get_user])])

    engine = next(
        provider.instance for provider in db_module.providers if provider.key is AsyncEngine and provider.instance is not None
    )
    asyncio.run(_create_schema(engine))

    user_id = asyncio.run(app.execute(CreateUser(email="u@example.com", name="User")))
    payload = asyncio.run(app.execute(GetUser(user_id=user_id)))

    assert user_id == 1
    assert payload == {"email": "u@example.com", "name": "User"}


def test_db_session_middleware_sets_context_session() -> None:
    db_module = sqlalchemy_module(SQLAlchemySettings(url="sqlite+aiosqlite:///:memory:"))
    session_factory = next(provider.instance for provider in db_module.providers if provider.key is async_sessionmaker)
    assert session_factory is not None
    middleware = DBSessionMiddleware(session_factory)
    context = ExecutionContext()

    async def run() -> bool:
        async def call_next(message: object) -> bool:
            return context.db_session is not None and "db_session" in context.services

        return await middleware(context, object(), call_next)

    assert asyncio.run(run()) is True
    assert context.db_session is None


async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
