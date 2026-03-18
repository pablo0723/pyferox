# Observability

Phase 4 observability focuses on portable hooks, not vendor lock-in.

## Logging Hooks

Install framework logging hooks:

```python
from pyferox.logging.hooks import install_logging_hooks

install_logging_hooks(app, include_request_middleware=True)
```

What you get:

- startup/shutdown logs
- dispatch exception logs
- optional request middleware logs

## Tracing

Use `TracingMiddleware` and a trace collector:

```python
from pyferox.ops import InMemoryTraceCollector, TracingMiddleware

collector = InMemoryTraceCollector()
app.add_middleware(TracingMiddleware(collector))
```

Each span includes:

- message name
- request/trace IDs
- transport
- duration
- success/failure

## Metrics

Use `MetricsMiddleware` with any collector implementing:

- `increment(name, value=1.0, tags=None)`
- `observe(name, value, tags=None)`

Built-in in-memory collector:

```python
from pyferox.ops import InMemoryMetricsCollector, MetricsMiddleware

metrics = InMemoryMetricsCollector()
app.add_middleware(MetricsMiddleware(metrics))
```

Default metric keys:

- `pyferox.dispatch.total`
- `pyferox.dispatch.success`
- `pyferox.dispatch.error`
- `pyferox.dispatch.duration_ms`

## Operational Diagnostics

Collect combined diagnostics payload:

```python
from pyferox.ops import collect_operational_diagnostics

payload = await collect_operational_diagnostics(
    health_registry=health,
    trace_collector=trace_collector,
    metrics_collector=metrics_collector,
)
```

This returns health, trace summary, and metrics snapshot in one payload.
