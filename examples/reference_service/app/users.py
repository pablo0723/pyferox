from __future__ import annotations

from pyferox.core import Module, StructCommand, StructQuery, handle, singleton


class InMemoryUserRepo:
    def __init__(self) -> None:
        self._rows: dict[int, dict[str, object]] = {}
        self._next_id = 1

    async def create(self, email: str, name: str) -> int:
        user_id = self._next_id
        self._next_id += 1
        self._rows[user_id] = {"id": user_id, "email": email, "name": name}
        return user_id

    async def get(self, user_id: int) -> dict[str, object]:
        return self._rows[user_id]


class CreateUser(StructCommand):
    email: str
    name: str


class GetUser(StructQuery):
    user_id: int


@handle(CreateUser)
async def create_user(cmd: CreateUser, users: InMemoryUserRepo) -> dict[str, int]:
    return {"id": await users.create(cmd.email, cmd.name)}


@handle(GetUser)
async def get_user(query: GetUser, users: InMemoryUserRepo) -> dict[str, object]:
    return await users.get(query.user_id)


users_module = Module(
    name="users",
    handlers=[create_user, get_user],
    providers=[singleton(InMemoryUserRepo())],
)
