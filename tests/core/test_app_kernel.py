from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox import App, Command, Event, Module, Query, ResolutionError, Scope, handle, listen, provider, singleton


class UserRepo:
    def __init__(self) -> None:
        self._next_id = 1
        self._store: dict[int, dict[str, str]] = {}

    async def create(self, email: str, name: str) -> int:
        user_id = self._next_id
        self._next_id += 1
        self._store[user_id] = {"email": email, "name": name}
        return user_id

    async def get(self, user_id: int) -> dict[str, str]:
        return self._store[user_id]


@dataclass(slots=True)
class CreateUser(Command):
    email: str
    name: str


@dataclass(slots=True)
class GetUser(Query):
    user_id: int


@handle(CreateUser)
async def create_user(cmd: CreateUser, users: UserRepo) -> int:
    return await users.create(cmd.email, cmd.name)


@handle(GetUser)
async def get_user(query: GetUser, users: UserRepo) -> dict[str, str]:
    return await users.get(query.user_id)


def test_command_and_query_flow() -> None:
    repo = UserRepo()
    users_module = Module(
        handlers=[create_user, get_user],
        providers=[singleton(repo)],
    )
    app = App(modules=[users_module])

    user_id = asyncio.run(app.execute(CreateUser(email="a@x.com", name="Ann")))
    payload = asyncio.run(app.execute(GetUser(user_id=user_id)))

    assert user_id == 1
    assert payload == {"email": "a@x.com", "name": "Ann"}


@dataclass(slots=True)
class UserCreated(Event):
    user_id: int


class RequestContext:
    pass


def test_event_listeners_share_scope_cache() -> None:
    seen: list[int] = []

    @listen(UserCreated)
    async def first(evt: UserCreated, ctx: RequestContext) -> None:
        seen.append(id(ctx))

    @listen(UserCreated)
    async def second(evt: UserCreated, ctx: RequestContext) -> None:
        seen.append(id(ctx))

    module = Module(
        listeners=[first, second],
        providers=[provider(RequestContext, lambda: RequestContext(), scope=Scope.REQUEST)],
    )
    app = App(modules=[module])

    asyncio.run(app.publish(UserCreated(user_id=7)))

    assert len(seen) == 2
    assert seen[0] == seen[1]


def test_execute_requires_registered_handler() -> None:
    app = App()
    with pytest.raises(LookupError):
        asyncio.run(app.execute(CreateUser(email="x@y.com", name="X")))


@dataclass(slots=True)
class Ping(Command):
    value: str


@handle(Ping)
async def invalid_handler(msg: Ping, dep) -> str:  # type: ignore[no-untyped-def]
    return dep


def test_dependency_annotation_required() -> None:
    app = App(modules=[Module(handlers=[invalid_handler])])
    with pytest.raises(ResolutionError):
        asyncio.run(app.execute(Ping(value="ok")))

