# PyFerOx

Transport-agnostic, async-first Python service application framework.

PyFerOx focuses on modular backend architecture where HTTP is one transport among many.  
Applications are built around commands, queries, events, services, and repositories.

## Current phase

Phase 1 foundation baseline is implemented (see `phase1_audit.md` for done/partial/missing details):

- Application kernel + lifecycle hooks (`startup` / `shutdown` / `lifespan`)
- Module system with imports and lifecycle hooks
- Handler registry + dispatcher pipeline
- Command/query/event abstractions
- DI container with application/request/job scopes
- Execution context (`request_id`, `trace_id`, `current_user`, metadata)
- Middleware/interceptor pipeline + pre/post hooks
- Typed config system (`AppConfig`, `DatabaseConfig`, `HttpConfig`) with env/profile loading + pluggable secret providers
- Msgspec-backed validation/schema runtime (`SchemaModel`, `parse_input`, `serialize_output`, `TypedSchema`, `ValidationError`)
- Unified error model with stable transport payload (`type`, `error`, `details`)
- Result/response models (`Success`, `Paginated`, `Empty`, `Streamed`)
- Logging middleware hooks (`RequestLoggingMiddleware`)
- Basic auth contracts (`Identity`, `Principal`, `AuthBackend`, `PermissionChecker`)
- HTTP adapter (`HTTPAdapter`) with typed route-to-message mapping, auth/permission checks, streamed responses
- SQLAlchemy integration (`sqlalchemy_module`, `UnitOfWork`, `Repository`)
- CLI bootstrap (`pyferox create-project`, `create-module`, `run-dev`, `inspect-config`)
- Testing utilities (`create_test_app`, `TestHTTPClient`, `FakeDispatcher`)

## Quickstart

```python
from pyferox import App, Command, Module, Query, handle, singleton


class UserRepo:
    async def create(self, email: str, name: str) -> int:
        return 1

    async def get(self, user_id: int) -> dict:
        return {"id": user_id, "email": "test@example.com", "name": "User"}


class CreateUser(Command):
    email: str
    name: str


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

## HTTP transport (ASGI)

```python
from pyferox import HTTPAdapter

http = HTTPAdapter(app)
http.command("POST", "/users", CreateUser, status_code=201)
http.query("GET", "/users/{user_id}", GetUser)
```

Use with any ASGI server, for example:

```bash
uvicorn your_module:http
```

## CLI bootstrap

```bash
pyferox create-project demo_service
pyferox create-module users --project demo_service/app
pyferox run-dev --target app.main:http
```

## Install

```bash
pip install pyferox
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
