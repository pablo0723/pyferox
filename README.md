# PyFerOx

Transport-agnostic, async-first Python service application framework.

PyFerOx focuses on modular backend architecture where HTTP is one transport among many.  
Applications are built around commands, queries, events, services, and repositories.

## Current phase

Phase 1 foundation is implemented:

- Application kernel (`App`)
- Module system (`Module`)
- Command/query handlers (`@handle`)
- Local event listeners (`@listen`)
- Lightweight dependency injection with scopes

## Quickstart

```python
from dataclasses import dataclass

from pyferox import App, Command, Module, Query, handle, singleton


class UserRepo:
    async def create(self, email: str, name: str) -> int:
        return 1

    async def get(self, user_id: int) -> dict:
        return {"id": user_id, "email": "test@example.com", "name": "User"}


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
async def get_user(query: GetUser, users: UserRepo) -> dict:
    return await users.get(query.user_id)


app = App(
    modules=[
        Module(
            handlers=[create_user, get_user],
            providers=[singleton(UserRepo())],
        )
    ]
)
```

Any transport adapter (HTTP, RPC, CLI, worker, queue) can call the same API:

- `await app.execute(command_or_query)`
- `await app.publish(event)`

## Install

```bash
pip install pyferox
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
