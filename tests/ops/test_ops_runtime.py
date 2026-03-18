from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pyferox.core import ExecutionContext
from pyferox.ops import (
    CheckStatus,
    HealthRegistry,
    InMemoryMetricsCollector,
    InMemoryTraceCollector,
    MetricsMiddleware,
    TracingMiddleware,
    collect_operational_diagnostics,
)


def test_health_registry_liveness_and_readiness_reports() -> None:
    registry = HealthRegistry()
    registry.add_liveness("live", lambda: True)
    registry.add_readiness("db", lambda: {"ok": False, "reason": "down"})

    async def run() -> tuple[bool, bool, str]:
        live = await registry.run_liveness()
        ready = await registry.run_readiness()
        return live.ok, ready.ok, ready.checks[0].status.value

    live_ok, ready_ok, ready_status = asyncio.run(run())
    assert live_ok is True
    assert ready_ok is False
    assert ready_status == CheckStatus.FAIL.value


def test_health_registry_ensure_ready_raises() -> None:
    registry = HealthRegistry()
    registry.add_readiness("service", lambda: False)
    with pytest.raises(RuntimeError):
        asyncio.run(registry.ensure_ready())


def test_tracing_middleware_records_success_and_failure() -> None:
    collector = InMemoryTraceCollector()
    middleware = TracingMiddleware(collector)
    context = ExecutionContext(request_id="r1", trace_id="t1", transport="internal")

    async def success(_: object) -> str:
        return "ok"

    result = asyncio.run(middleware(context, object(), success))
    assert result == "ok"
    assert collector.spans[0].success is True

    async def fail(_: object) -> str:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        asyncio.run(middleware(context, object(), fail))
    assert collector.spans[-1].success is False
    assert collector.spans[-1].error == "boom"


def test_collect_operational_diagnostics_combines_health_and_trace_data() -> None:
    registry = HealthRegistry()
    registry.add_liveness("live", lambda: True)
    registry.add_readiness("ready", lambda: True)
    collector = InMemoryTraceCollector()

    payload = asyncio.run(
        collect_operational_diagnostics(
            health_registry=registry,
            trace_collector=collector,
        )
    )
    assert payload["ok"] is True
    assert payload["liveness"]["ok"] is True
    assert payload["readiness"]["ok"] is True
    assert payload["traces"]["count"] == 0


@dataclass(slots=True)
class Ping:
    value: str = "x"


def test_metrics_middleware_records_success_and_failure() -> None:
    collector = InMemoryMetricsCollector()
    middleware = MetricsMiddleware(collector)
    context = ExecutionContext(request_id="r1", trace_id="t1", transport="internal")

    async def success(_: object) -> str:
        return "ok"

    result = asyncio.run(middleware(context, Ping(), success))
    assert result == "ok"

    async def fail(_: object) -> str:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(middleware(context, Ping(), fail))

    payload = collector.to_payload()
    counter_names = {item["name"] for item in payload["counters"]}
    assert "pyferox.dispatch.total" in counter_names
    assert "pyferox.dispatch.success" in counter_names
    assert "pyferox.dispatch.error" in counter_names
    assert payload["observation_count"] >= 2


def test_collect_operational_diagnostics_includes_metrics_summary() -> None:
    metrics = InMemoryMetricsCollector()
    metrics.increment("pyferox.dispatch.total", tags={"transport": "http"})
    metrics.observe("pyferox.dispatch.duration_ms", 1.23, tags={"transport": "http"})

    payload = asyncio.run(collect_operational_diagnostics(metrics_collector=metrics))
    assert payload["ok"] is True
    assert payload["metrics"]["counter_count"] == 1
    assert payload["metrics"]["observation_count"] == 1
