from __future__ import annotations

import asyncio

import pytest

from pyferox.core import ExecutionContext
from pyferox.ops import CheckStatus, HealthRegistry, InMemoryTraceCollector, TracingMiddleware, collect_operational_diagnostics


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
