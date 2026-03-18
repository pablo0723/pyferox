# PyFerOx

Transport-agnostic, async-first Python service framework built around:

- typed command/query/event contracts
- modular composition
- execution middleware + lifecycle hooks
- pluggable transports (HTTP, jobs/worker, RPC, scheduler)

## Project Status

Phase 1-3 implementation is complete according to repository audits:

- [Phase 1 audit](phase1_audit.md)
- [Phase 2 audit](phase2_audit.md)
- [Phase 3 audit](phase3_audit.md)

## Documentation

Full user docs are in [`docs/`](docs/README.md).

Recommended start:

1. [Quickstart](docs/quickstart.md)
2. [Core Concepts](docs/core-concepts.md)
3. [HTTP, Auth, OpenAPI](docs/http-auth-openapi.md)
4. [Persistence (SQLAlchemy)](docs/persistence-sqlalchemy.md)
5. [Background and Distributed Runtime](docs/background-and-distributed-runtime.md)
6. [Testing](docs/testing.md)
7. [Configuration](docs/configuration.md)
8. [CLI Reference](docs/cli.md)
9. [Operations and Tuning](docs/operations-and-tuning.md)

## Install

```bash
pip install -e ".[dev,http]"
```

## Minimal Example

```python
from pyferox.core import App, Module, StructCommand, StructQuery, handle, singleton
from pyferox.http import HTTPAdapter


class UserRepo:
    async def create(self, email: str, name: str) -> int:
        return 1

    async def get(self, user_id: int) -> dict[str, str]:
        return {"id": str(user_id), "email": "user@example.com", "name": "User"}


class CreateUser(StructCommand):
    email: str
    name: str


class GetUser(StructQuery):
    user_id: int


@handle(CreateUser)
async def create_user(cmd: CreateUser, users: UserRepo) -> dict[str, int]:
    return {"id": await users.create(cmd.email, cmd.name)}


@handle(GetUser)
async def get_user(query: GetUser, users: UserRepo) -> dict[str, str]:
    return await users.get(query.user_id)


app = App(modules=[Module(handlers=[create_user, get_user], providers=[singleton(UserRepo())])])
http = HTTPAdapter(app)
http.command("POST", "/users", CreateUser, status_code=201)
http.query("GET", "/users/{user_id}", GetUser)
```

PyFerOx is msgspec-backed. For new transport-facing contracts, prefer `StructCommand` / `StructQuery` / `StructEvent`. Dataclass contracts are still supported, but they are not the primary style to teach in user-facing examples.

Run:

```bash
uvicorn app.main:http --reload
```

Or scaffold first:

```bash
pyferox create-project demo_service --template api
cd demo_service
pyferox run-dev --target app.main:http
```
