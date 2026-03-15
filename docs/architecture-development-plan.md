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

- `App` kernel
- `Module` registration
- `@handle` command/query handlers
- `@listen` event listeners (local mode)
- Type-based DI container with scopes (`APP`, `REQUEST`, `JOB`)
- Basic tests for dispatch + scope behavior

### Phase 2

- HTTP transport adapter (ASGI)
- Request-scoped DI middleware
- Input/output contract layer (Pydantic or msgspec)
- Error mapping contract

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

1. Add `http` package with minimal ASGI adapter calling `App.execute`.
2. Define standardized application errors and adapter-level error mapping.
3. Add SQLAlchemy module with async session factory + UoW.
4. Add sample app in `examples/demo_app` using Users + Billing modules.
5. Add docs for module authoring conventions and best practices.
