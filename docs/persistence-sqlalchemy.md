# Persistence (SQLAlchemy)

## What PyFerOx Provides

PyFerOx does not replace SQLAlchemy. It provides:

- `sqlalchemy_module(...)` for DI/lifecycle wiring
- `UnitOfWork` for transaction boundaries
- `DBSessionMiddleware` for request/session context wiring
- `Repository` base class
- migration wrappers around Alembic

## Configure Database Module

```python
from pyferox.core import App, Module
from pyferox.db import SQLAlchemySettings, sqlalchemy_module

db_module = sqlalchemy_module(
    SQLAlchemySettings(url="sqlite+aiosqlite:///./app.db", echo=False)
)
app = App(modules=[db_module, Module(handlers=[...])])
```

`sqlalchemy_module` registers:

- `AsyncEngine` singleton
- `async_sessionmaker` singleton
- `AsyncSession` provider (scoped)
- `UnitOfWork` provider (scoped)

Engine is disposed on app shutdown hook.

## Use UnitOfWork in Handlers

```python
from sqlalchemy import select
from pyferox.core import Query, StructCommand, handle
from pyferox.db import UnitOfWork


class CreateUser(StructCommand):
    email: str
    name: str


@handle(CreateUser)
async def create_user(cmd: CreateUser, uow: UnitOfWork) -> int:
    async with uow:
        assert uow.session is not None
        row = UserRow(email=cmd.email, name=cmd.name)
        uow.session.add(row)
        await uow.session.flush()
        return int(row.id)
```

`UnitOfWork` behavior:

- commits on successful `__aexit__`
- rollbacks on exception
- closes session always

## Request-Level Session Access

If you need context-level session access in middleware or handlers:

```python
from pyferox.db import DBSessionMiddleware

app.add_middleware(DBSessionMiddleware(session_factory))
```

It stores session in:

- `context.db_session`
- `context.services["db_session"]`

and removes/cleans it after execution.

## Repository Base

```python
from pyferox.db import Repository


class UserRepository(Repository[UserRow, int]):
    async def get_by_id(self, user_id: int) -> UserRow | None:
        ...
```

The base class is intentionally minimal; keep your SQLAlchemy patterns explicit.

## Migrations

CLI wrappers (require `alembic` in PATH):

```bash
pyferox migrate-init --directory migrations
pyferox migrate-revision -m "create users" --autogenerate
pyferox migrate-upgrade --revision head
pyferox migrate-current
pyferox migrate-downgrade --revision -1
```

Equivalent Python APIs:

- `migration_init(...)`
- `migration_revision(...)`
- `migration_upgrade(...)`
- `migration_downgrade(...)`
- `migration_current(...)`

## Practical Guidance

- Keep transaction boundaries inside handlers/services through `UnitOfWork`.
- Avoid global sessions.
- Use `Scope.REQUEST` for HTTP-style message execution.
- Turn `echo=True` only for local debugging.
