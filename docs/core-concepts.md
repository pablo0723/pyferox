# Core Concepts

## Import Strategy

Use explicit module imports to keep boundaries clear:

```python
from pyferox.core import App, Module, Command, Query, handle
from pyferox.db import UnitOfWork
from pyferox.http import HTTPAdapter
```

## Application Kernel

`App` is the runtime root.

- Loads modules, handlers, providers, and middleware
- Owns dispatcher, DI container, and lifecycle hooks
- Executes message handlers and publishes events

Main calls:

- `await app.execute(message)`
- `await app.execute_with_context(message, context=...)`
- `await app.publish(event)`
- `await app.startup()` / `await app.shutdown()`
- `async with app.lifespan(): ...`

## Modules

`Module` is the composition unit.

You can register:

- `handlers`
- `listeners`
- `providers`
- `middlewares`
- `imports` (module dependencies)
- lifecycle hooks (`on_init`, `on_startup`, `on_shutdown`)

Example:

```python
module = Module(
    name="users",
    handlers=[create_user, get_user],
    providers=[singleton(UserRepo())],
)
```

## Contracts: Command, Query, Event

- `Command`: write-side operation
- `Query`: read-side operation
- `Event`: publish/subscribe event

Important distinction:

- `Command` / `Query` / `Event` provide framework semantics
- `msgspec.Struct` provides msgspec-native data model behavior

`Command` itself is not a subclass of `msgspec.Struct`. In the current implementation it inherits from `Message`.

To keep the public API framework-shaped, PyFerOx provides framework-owned msgspec-backed bases:

- `StructCommand`
- `StructQuery`
- `StructEvent`

Recommended style for new code is msgspec-backed contracts:

```python
from pyferox.core import StructCommand, StructQuery


class CreateUser(StructCommand):
    email: str
    name: str


class GetUser(StructQuery):
    user_id: int
```

This gives you direct construction plus fast msgspec-based parsing/serialization behavior without exposing `msgspec.Struct` in every user example. Dataclass contracts are also supported, but they should be treated as a compatibility or ergonomics option, not the default style shown to new users. Keep business logic in handlers, not in contract classes.

Use `@contract(...)` metadata if needed:

```python
from pyferox.core import StructQuery, contract


@contract(audience="internal", version=1)
class GetUser(StructQuery):
    user_id: int
```

## Handler Registration

Use decorators:

- `@handle(MessageType)` for command/query handlers
- `@listen(EventType)` for event listeners

The dispatcher maps one handler per command/query type and many listeners per event type.

## Dependency Injection

Providers are registered with scopes:

- `Scope.APP`
- `Scope.REQUEST`
- `Scope.JOB`
- `Scope.TRANSIENT`

Helpers:

- `singleton(instance)`
- `provider(TypeKey, factory, scope=...)`

Injected dependencies are resolved from handler parameter type annotations.

## Execution Context

`ExecutionContext` carries per-execution metadata:

- `request_id`
- `trace_id`
- `correlation_id`
- `transport` (`internal`, `http`, `rpc`, `event`, ...)
- `current_user`
- `db_session`
- `services` and `metadata`

You can inject it into handlers:

```python
from pyferox.core import ExecutionContext


@handle(GetUser)
async def get_user(query: GetUser, context: ExecutionContext):
    return {"request_id": context.request_id}
```

## Middleware and Hooks

Execution middleware signature:

```python
async def middleware(context, message, call_next):
    return await call_next(message)
```

Hook types:

- pre-hook: before dispatch
- post-hook: always after dispatch
- exception-hook: on handler exception

Register via `app.add_middleware`, `app.add_pre_hook`, `app.add_post_hook`, `app.add_exception_hook`.

## Results

Supported return types:

- plain dict/list/scalar
- msgspec structs, dataclasses, and plain serializable objects
- `Response(data=..., status_code=..., headers=...)`
- `Paginated(...)`
- `Streamed(...)`
- `None` (normalized to `{}` for HTTP)

## Error Model

Main error classes:

- `ValidationError`
- `NotFoundError`
- `ConflictError`
- `ForbiddenError`
- `UnauthorizedError`
- `PermissionDeniedError`
- `InfrastructureError`

Map to transport payloads with:

```python
status, payload = map_exception_to_transport(exc)
```
