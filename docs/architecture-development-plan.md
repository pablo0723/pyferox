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

### Phase 1 (implemented; mandatory baseline)

Mandatory checklist (must exist in Phase 1):

1. Config system
   - env loading (`.env`, `.env.<profile>`)
   - typed settings (`AppConfig`, `DatabaseConfig`, `HttpConfig`)
   - profiles (`dev` / `test` / `prod`)
   - secret handling interface (`SecretProvider`, env/dict/file/chained providers)
2. Validation / schema layer
   - command/query input parsing and coercion
   - output serialization
   - validation error formatting
   - typed schema wrapper (`TypedSchema`) on top of msgspec runtime
3. Request / execution context
   - request id, trace id
   - current user
   - db session
   - app service bag
4. Error model
   - framework exceptions
   - domain exceptions
   - auth/validation/not-found/conflict/forbidden categories
   - transport mapping with stable error payload shape (`type`, `error`, `details`)
5. Response model / result handling
   - success result (`Success`)
   - paginated result (`Paginated`)
   - empty result (`Empty`)
   - streamed result contract (`Streamed`; HTTP adapter support)
6. Middleware / interceptor system
   - middleware chain
   - pre/post execution hooks
   - extension points for logging/auth/tracing/rate-limiting/metrics/db lifecycle
7. Handler registry / dispatcher
   - registration + lookup
   - execution pipeline
   - pre/post hooks
   - sync/async policy
8. App lifecycle
   - startup/shutdown hooks
   - module init hooks
   - resource cleanup
   - lifespan context manager
9. Testing utilities
   - test app factory
   - HTTP test client
   - fake dispatcher
   - dependency overrides
10. Logging integration
   - structured request logging hooks
   - exception logging hooks
11. Basic auth contract
   - identity/principal contracts
   - auth backend interface
   - permission checker interface
12. Project scaffolding / CLI bootstrap
   - `create-project`
   - `create-module`
   - `run-dev`

Phase 1 grouped deliverables:

- Core runtime:
  - Application kernel
  - Module system
  - Handler registry / dispatcher
  - Command / Query / Event abstractions
  - Dependency injection
  - App lifecycle hooks
  - Execution context
- Developer foundation:
  - Config system
  - Validation / schema layer
  - Error model
  - Result / response model
  - Middleware / interceptor pipeline
  - Logging hooks
- First transport + persistence:
  - HTTP adapter
  - SQLAlchemy integration
  - Unit of Work base
  - Repository base abstractions
- Dev experience:
  - CLI bootstrap
  - Testing utilities

### Phase 2

- Production-grade transport adapters (HTTP/RPC/CLI worker convergence)
- Additional schema backends (Pydantic v2 adapter on top of default msgspec runtime)
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
