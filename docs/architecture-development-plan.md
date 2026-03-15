# PyFerOx Architecture and Development Plan

## 1. Goal

Build a modular Python service framework where business logic is transport-agnostic and reusable across:

- HTTP APIs
- RPC
- CLI
- Workers/jobs
- Queues

## 2. Architectural shape

Core flow:

1. Transport adapter accepts input.
2. Adapter maps input to `Command` or `Query`.
3. `App.execute(...)` routes to a registered handler.
4. Handler uses services/repositories via DI.
5. Handler emits `Event` where needed.
6. Event listeners react asynchronously.

Layering:

- `core`: kernel, module system, handlers, DI, events
- `db`: repository base, unit-of-work, transaction boundaries
- `http`: request mapping + response rendering
- `rpc`: request/response protocol adapter
- `cli`: command parser to app handlers
- `jobs`: scheduler + retry orchestration
- `queue`: consumer/producer integration

## 3. Phase plan

### Phase 1 (implemented in this repo)

- Core runtime:
  - `App` kernel, lifecycle hooks, module imports
  - Handler registry + dispatcher execution pipeline
  - Command/query/event handling (`@handle`, `@listen`)
  - DI scopes (`APP`, `REQUEST`, `JOB`)
  - Execution context and middleware/interceptor pipeline
- Developer foundation:
  - Typed config + env/profile loading (`dev`/`test`/`prod`)
  - Validation/schema parsing + output serialization
  - Unified framework/domain errors and transport mapping
  - Result models (`Success`, `Paginated`, `Empty`)
  - Logging middleware hooks
  - Auth contracts (identity/principal/backend/permission checker)
- First transport + persistence:
  - ASGI HTTP adapter (`HTTPAdapter`)
  - SQLAlchemy integration (`sqlalchemy_module`, `UnitOfWork`, `Repository`)
- Dev experience:
  - CLI bootstrap (`create-project`, `create-module`, `run-dev`)
  - Testing utilities (`create_test_app`, `TestHTTPClient`, `FakeDispatcher`)

### Phase 2

- Production-grade transport adapters (HTTP/RPC/CLI worker convergence)
- Extended schema engine (Pydantic/msgspec backends)
- Auth module implementation (tokens, sessions, policies)
- Metrics/tracing exporters and richer observability

### Phase 3

- SQLAlchemy integration module
- Repository base class
- Unit of Work and transaction context
- Alembic integration commands

### Phase 4

- CLI transport that auto-discovers handlers
- Job runner with retries, delayed execution, idempotency keys
- Cron-like scheduler module

### Phase 5

- Distributed event mode and queue adapters:
  - Redis Streams
  - NATS
  - Kafka
  - RabbitMQ

## 4. Technical standards

- Python 3.12+
- Async-first APIs (`async def` handlers/listeners)
- Strong typing across public interfaces
- No business logic in transport layer
- Each module tested with unit tests first, then adapter integration tests

## 5. Near-term implementation backlog

1. Add production-ready sample app in `examples/demo_app`.
2. Add pluggable auth implementation module on top of current contracts.
3. Add RPC/queue adapters with shared execution context propagation.
4. Add migration wrapper and database test transaction fixtures.
5. Add module authoring guide and architecture decision records.
