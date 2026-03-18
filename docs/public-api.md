# Public API and Compatibility

This document defines the current public API tiers for Phase 4 stabilization.

## Stability Tiers

- `stable`: safe for regular application use, backwards-compatible within major versions
- `provisional`: public but still allowed to evolve with deprecation notes
- `internal`: not part of the public contract

## Canonical Import Paths

Use explicit module imports for framework-facing code:

```python
from pyferox.core import App, Module, StructCommand, StructQuery, handle
from pyferox.http import HTTPAdapter
```

Use subsystem namespaces for runtime families:

```python
from pyferox.rpc import RPCClient
from pyferox.ops import HealthRegistry
```

## Compatibility Matrix (Phase 4)

| Area | Symbols | Tier | Notes |
|---|---|---|---|
| Core app runtime | `App`, `Module`, `ExecutionContext` | stable | Canonical runtime contracts. |
| Contracts | `StructCommand`, `StructQuery`, `StructEvent` | stable | Preferred transport-facing contract style. |
| Legacy contracts | `Command`, `Query`, `Event` | provisional | Supported; msgspec-backed struct variants are recommended. |
| Dispatch and DI | `handle`, `listen`, `provider`, `singleton`, `Scope` | stable | Main composition API. |
| HTTP transport | `HTTPAdapter` | stable | Main HTTP adapter contract. |
| Error mapping | `ValidationError`, `DomainError`, `InfrastructureError`, `map_exception_to_transport` | stable | Transport mapping behavior documented in error taxonomy. |
| Jobs/events/reliability | `JobDispatcher`, `LocalJobWorker`, `DistributedEventBus`, `RetryPolicy`, `InMemoryIdempotencyStore` | provisional | Public and usable, still expanding. |
| RPC | `RPCClient`, `RPCServer`, `RPCTransport`, `RPCRequest`, `RPCResponse` | provisional | Public adapter surface, wire policy can evolve with migration notes. |
| Scheduler/workflow | `SchedulerRuntime`, `Workflow`, `WorkflowStep` | provisional | Public runtime APIs, still under active hardening. |
| Internal helpers | private functions/classes in `pyferox.*.runtime` not re-exported | internal | No compatibility guarantees. |

## Deprecation Policy

- Do not remove stable API in patch/minor releases.
- For renames/removals in provisional API, provide:
  - a migration note
  - a compatibility alias when feasible
  - tests for both old and new behavior during transition
- Track deprecations in release notes and docs.

## Core Boundary Rule

Core should stay small:

- core contracts and runtime in `pyferox.core`
- transport/runtime families as focused modules (`http`, `rpc`, `jobs`, `events`, `ops`)
- app-specific patterns should live in user projects or extensions
