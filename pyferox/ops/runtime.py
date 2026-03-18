"""Operational hooks: health/readiness checks and tracing middleware."""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable, Protocol

from pyferox.core import ExecutionContext

CheckFn = Callable[[], Awaitable[bool | dict[str, Any]] | bool | dict[str, Any]]


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(slots=True)
class HealthCheckResult:
    name: str
    status: CheckStatus
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == CheckStatus.PASS


@dataclass(slots=True)
class HealthReport:
    ok: bool
    checks: list[HealthCheckResult]

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "duration_ms": round(check.duration_ms, 3),
                    "details": check.details,
                }
                for check in self.checks
            ],
        }


class HealthRegistry:
    def __init__(self) -> None:
        self._liveness: dict[str, CheckFn] = {}
        self._readiness: dict[str, CheckFn] = {}

    def add_liveness(self, name: str, fn: CheckFn) -> None:
        self._liveness[name] = fn

    def add_readiness(self, name: str, fn: CheckFn) -> None:
        self._readiness[name] = fn

    async def run_liveness(self) -> HealthReport:
        return await self._run_checks(self._liveness)

    async def run_readiness(self) -> HealthReport:
        return await self._run_checks(self._readiness)

    async def ensure_ready(self) -> None:
        report = await self.run_readiness()
        if not report.ok:
            raise RuntimeError("Readiness checks failed")

    async def _run_checks(self, checks: dict[str, CheckFn]) -> HealthReport:
        results: list[HealthCheckResult] = []
        for name, fn in checks.items():
            start = time.perf_counter()
            try:
                raw = fn()
                if inspect.isawaitable(raw):
                    raw = await raw
                ok, details = _coerce_check_result(raw)
                status = CheckStatus.PASS if ok else CheckStatus.FAIL
                duration_ms = (time.perf_counter() - start) * 1000.0
                results.append(HealthCheckResult(name=name, status=status, duration_ms=duration_ms, details=details))
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000.0
                results.append(
                    HealthCheckResult(
                        name=name,
                        status=CheckStatus.FAIL,
                        duration_ms=duration_ms,
                        details={"error": str(exc)},
                    )
                )
        return HealthReport(ok=all(item.ok for item in results), checks=results)


def _coerce_check_result(raw: bool | dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if isinstance(raw, bool):
        return raw, {}
    if isinstance(raw, dict):
        ok = bool(raw.get("ok", True))
        details = {str(k): v for k, v in raw.items() if k != "ok"}
        return ok, details
    return False, {"error": f"Unsupported check result type: {type(raw)}"}


@dataclass(slots=True)
class TraceSpan:
    name: str
    request_id: str
    trace_id: str | None
    transport: str
    duration_ms: float
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TraceCollector(Protocol):
    def record(self, span: TraceSpan) -> None:
        ...


class InMemoryTraceCollector:
    def __init__(self) -> None:
        self.spans: list[TraceSpan] = []

    def record(self, span: TraceSpan) -> None:
        self.spans.append(span)


class MetricsCollector(Protocol):
    def increment(self, name: str, value: float = 1.0, *, tags: dict[str, str] | None = None) -> None:
        ...

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        ...


@dataclass(slots=True)
class MetricObservation:
    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)


class InMemoryMetricsCollector:
    def __init__(self) -> None:
        self.counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self.observations: list[MetricObservation] = []

    def increment(self, name: str, value: float = 1.0, *, tags: dict[str, str] | None = None) -> None:
        normalized = _metric_tags(tags)
        key = (name, tuple(sorted(normalized.items())))
        self.counters[key] = self.counters.get(key, 0.0) + float(value)

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        self.observations.append(MetricObservation(name=name, value=float(value), tags=_metric_tags(tags)))

    def to_payload(self) -> dict[str, Any]:
        counters = [
            {"name": name, "value": value, "tags": dict(tags)}
            for (name, tags), value in sorted(self.counters.items())
        ]
        observations = [
            {"name": item.name, "value": round(item.value, 3), "tags": item.tags}
            for item in self.observations[-10:]
        ]
        return {
            "counter_count": len(counters),
            "observation_count": len(self.observations),
            "counters": counters,
            "latest_observations": observations,
        }


class MetricsMiddleware:
    """Execution middleware producing counters/timing metrics per dispatch."""

    def __init__(self, collector: MetricsCollector, *, metric_prefix: str = "pyferox.dispatch") -> None:
        self.collector = collector
        self.metric_prefix = metric_prefix

    async def __call__(self, context: ExecutionContext, message: Any, call_next: Any) -> Any:
        start = time.perf_counter()
        tags = {"message": type(message).__name__, "transport": context.transport}
        self.collector.increment(f"{self.metric_prefix}.total", tags=tags)
        try:
            result = await call_next(message)
            self.collector.increment(f"{self.metric_prefix}.success", tags=tags)
            return result
        except Exception:
            self.collector.increment(f"{self.metric_prefix}.error", tags=tags)
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.collector.observe(f"{self.metric_prefix}.duration_ms", duration_ms, tags=tags)


class TracingMiddleware:
    """Execution middleware producing timing spans for each dispatch."""

    def __init__(self, collector: TraceCollector) -> None:
        self.collector = collector

    async def __call__(self, context: ExecutionContext, message: Any, call_next: Any) -> Any:
        start = time.perf_counter()
        name = type(message).__name__
        try:
            result = await call_next(message)
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.collector.record(
                TraceSpan(
                    name=name,
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    transport=context.transport,
                    duration_ms=duration_ms,
                    success=True,
                )
            )
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.collector.record(
                TraceSpan(
                    name=name,
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    transport=context.transport,
                    duration_ms=duration_ms,
                    success=False,
                    error=str(exc),
                )
            )
            raise


async def collect_operational_diagnostics(
    *,
    health_registry: HealthRegistry | None = None,
    trace_collector: InMemoryTraceCollector | None = None,
    metrics_collector: InMemoryMetricsCollector | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}

    if health_registry is not None:
        liveness = await health_registry.run_liveness()
        readiness = await health_registry.run_readiness()
        payload["liveness"] = liveness.to_payload()
        payload["readiness"] = readiness.to_payload()
        payload["ok"] = bool(liveness.ok and readiness.ok)

    if trace_collector is not None:
        spans = list(trace_collector.spans)
        failures = [span for span in spans if not span.success]
        payload["traces"] = {
            "count": len(spans),
            "failed_count": len(failures),
        }
        if spans:
            payload["latest_trace"] = {
                "name": spans[-1].name,
                "transport": spans[-1].transport,
                "success": spans[-1].success,
                "duration_ms": round(spans[-1].duration_ms, 3),
            }

    if metrics_collector is not None:
        payload["metrics"] = metrics_collector.to_payload()

    payload.setdefault("ok", True)
    return payload


def _metric_tags(tags: dict[str, str] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in (tags or {}).items()}
