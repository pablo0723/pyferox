from __future__ import annotations

import asyncio

from pyferox.core import ExecutionContext
from pyferox.ops import (
    HealthRegistry,
    InMemoryMetricsCollector,
    InMemoryTraceCollector,
    MetricsMiddleware,
    TracingMiddleware,
    collect_operational_diagnostics,
)


def test_health_registry_async_exception_and_unsupported_result_branches() -> None:
    registry = HealthRegistry()

    async def async_ok() -> bool:
        return True

    def explode() -> bool:
        raise RuntimeError("down")

    def unsupported() -> str:
        return "bad"

    registry.add_liveness("async", async_ok)
    registry.add_liveness("explode", explode)
    registry.add_liveness("unsupported", unsupported)  # type: ignore[arg-type]

    report = asyncio.run(registry.run_liveness())
    assert report.ok is False
    statuses = {item.name: item.status.value for item in report.checks}
    assert statuses["async"] == "pass"
    assert statuses["explode"] == "fail"
    assert statuses["unsupported"] == "fail"


def test_health_registry_ensure_ready_success_branch() -> None:
    registry = HealthRegistry()
    registry.add_readiness("ok", lambda: True)
    asyncio.run(registry.ensure_ready())


def test_collect_operational_diagnostics_trace_only_and_latest_trace() -> None:
    collector = InMemoryTraceCollector()
    middleware = TracingMiddleware(collector)
    context = ExecutionContext(transport="internal")

    async def call_next(_: object) -> str:
        return "ok"

    asyncio.run(middleware(context, object(), call_next))
    payload = asyncio.run(collect_operational_diagnostics(trace_collector=collector))
    assert payload["ok"] is True
    assert payload["traces"]["count"] == 1
    assert payload["latest_trace"]["success"] is True


def test_metrics_collector_normalizes_tags_and_middleware_prefix() -> None:
    collector = InMemoryMetricsCollector()
    middleware = MetricsMiddleware(collector, metric_prefix="custom.dispatch")
    context = ExecutionContext(transport="rpc")

    async def call_next(_: object) -> str:
        return "ok"

    asyncio.run(middleware(context, object(), call_next))
    collector.increment("custom.counter", tags={"attempt": 1})  # type: ignore[arg-type]
    collector.observe("custom.observe", 2, tags={"ok": True})  # type: ignore[arg-type]

    payload = asyncio.run(collect_operational_diagnostics(metrics_collector=collector))
    assert payload["metrics"]["counter_count"] >= 2
    names = {item["name"] for item in payload["metrics"]["counters"]}
    assert "custom.dispatch.total" in names
    assert "custom.dispatch.success" in names
