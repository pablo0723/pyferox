# Operations and Tuning

## Logging Hooks

Install built-in hooks:

```python
from pyferox.logging.hooks import install_logging_hooks

install_logging_hooks(app)
```

This wires:

- app startup log
- app shutdown log
- dispatch exception log
- optional request logging middleware

Use your own logger:

```python
import logging
from pyferox.logging.hooks import install_logging_hooks

logger = logging.getLogger("my-service")
install_logging_hooks(app, logger=logger, include_request_middleware=True)
```

## Health and Operational Diagnostics

Register checks:

```python
from pyferox.ops import HealthRegistry

health = HealthRegistry()
health.add_liveness("runtime", lambda: True)
health.add_readiness("db", check_database)
```

Evaluate directly:

```python
report = await health.run_readiness()
if not report.ok:
    ...
```

Collect broader diagnostics:

```python
from pyferox.ops import InMemoryMetricsCollector, InMemoryTraceCollector, collect_operational_diagnostics

trace_collector = InMemoryTraceCollector()
metrics_collector = InMemoryMetricsCollector()
payload = await collect_operational_diagnostics(
    health_registry=health,
    trace_collector=trace_collector,
    metrics_collector=metrics_collector,
)
```

Expose via CLI:

```bash
pyferox health-check --target app.ops:health_registry
pyferox ops-diagnostics --target app.ops:runtime
```

## Retry and Idempotency Tuning

Tune retries with `RetryPolicy`:

- `max_attempts`
- `base_delay_seconds`
- `backoff_multiplier`
- `max_delay_seconds`
- `jitter_seconds`

Guidelines:

- low latency internal calls: small base delay, low attempts
- external dependencies: moderate attempts and capped exponential backoff
- high contention systems: add jitter

Use idempotency for duplicate suppression:

- jobs: `idempotency_key` in `JobDispatcher.enqueue(...)`
- RPC: `idempotency_key` in `RPCRequest`/`RPCClient.call(...)`

## Worker Tuning

Controls:

- `idle_timeout` in worker loop
- `poll_interval` in `WorkerRuntime.run_forever(...)`
- CLI `--max-iterations` for bounded runs

Guidelines:

- reduce polling interval for low-latency queue handling
- increase polling interval to reduce CPU usage on mostly idle workers
- use bounded iterations in CI or smoke checks

## Scheduler Tuning

Controls:

- `schedule_interval(interval_seconds=...)`
- `schedule_delayed(delay_seconds=...)`
- retry settings per task (`max_retries`) + global retry policy
- `run_forever(poll_interval=...)`

Guidelines:

- keep task functions short and non-blocking
- isolate long-running work into jobs/worker runtime
- use retries only for transient failures

## HTTP Tuning

Key options:

- `list_query(..., max_page_size=...)` for hard pagination caps
- OpenAPI route metadata for better API discoverability
- permission checks to avoid unauthorized processing

Guidelines:

- set conservative `max_page_size` defaults
- require explicit permissions on sensitive routes
- propagate request IDs (`x-request-id`, `x-trace-id`) through clients

## Metrics Middleware

Capture dispatch counters and latency:

```python
from pyferox.ops import InMemoryMetricsCollector, MetricsMiddleware

metrics = InMemoryMetricsCollector()
app.add_middleware(MetricsMiddleware(metrics))
```

Default metric names:

- `pyferox.dispatch.total`
- `pyferox.dispatch.success`
- `pyferox.dispatch.error`
- `pyferox.dispatch.duration_ms`

See [Observability](observability.md) for the full model.

## Benchmark Baselines

Run baseline benchmark suite:

```bash
python benchmarks/phase4_baseline.py
```

This measures startup time, dispatch throughput, and in-process HTTP adapter throughput.

## Database Tuning

Config knobs:

- `PYFEROX_DB_URL`
- `PYFEROX_DB_ECHO`

Guidelines:

- disable SQL echo in production
- keep transaction scopes tight (`async with uow`)
- avoid sharing sessions outside scoped execution

## Failure Semantics Cheat Sheet

- Domain/validation errors map to stable transport payloads.
- Unknown exceptions map to `internal_error` (HTTP 500).
- Job failures can be retried or marked failed based on policy and `max_retries`.
- Scheduler interval tasks continue after failures; delayed tasks do not repeat unless retried.
- Workflow failures may produce compensation and return `compensated` status.
