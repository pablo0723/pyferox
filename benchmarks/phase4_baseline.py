from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass

from pyferox.core import App, Module, StructQuery, handle
from pyferox.http import HTTPAdapter


class Ping(StructQuery):
    pass


@handle(Ping)
async def ping(_: Ping) -> dict[str, bool]:
    return {"ok": True}


@dataclass(slots=True)
class BenchmarkResult:
    startup_ms: float
    dispatch_rps: float
    http_rps: float
    iterations: int
    modules: int

    def to_payload(self) -> dict[str, float | int]:
        return {
            "startup_ms": round(self.startup_ms, 3),
            "dispatch_rps": round(self.dispatch_rps, 2),
            "http_rps": round(self.http_rps, 2),
            "iterations": self.iterations,
            "modules": self.modules,
        }


def build_app(modules: int) -> tuple[App, HTTPAdapter]:
    module_list: list[Module] = [Module(name="core", handlers=[ping])]
    for index in range(max(0, modules - 1)):
        module_list.append(Module(name=f"extra_{index}"))
    app = App(modules=module_list)
    http = HTTPAdapter(app)
    http.query("GET", "/ping", Ping)
    return app, http


async def bench_dispatch(app: App, iterations: int) -> float:
    for _ in range(500):
        await app.execute(Ping())
    started = time.perf_counter()
    for _ in range(iterations):
        await app.execute(Ping())
    duration = time.perf_counter() - started
    return iterations / duration


async def bench_http(http: HTTPAdapter, iterations: int) -> float:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ping",
        "query_string": b"",
        "headers": [],
    }

    async def call_once() -> int:
        sent: list[dict[str, object]] = []
        sent_request = False

        async def receive() -> dict[str, object]:
            nonlocal sent_request
            if sent_request:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await http(scope, receive, send)
        start = next(item for item in sent if item["type"] == "http.response.start")
        return int(start["status"])

    for _ in range(500):
        await call_once()
    started = time.perf_counter()
    for _ in range(iterations):
        status = await call_once()
        if status != 200:
            raise RuntimeError(f"Unexpected status code: {status}")
    duration = time.perf_counter() - started
    return iterations / duration


async def run(iterations: int, modules: int) -> BenchmarkResult:
    startup_started = time.perf_counter()
    app, http = build_app(modules)
    startup_ms = (time.perf_counter() - startup_started) * 1000.0
    dispatch_rps = await bench_dispatch(app, iterations)
    http_rps = await bench_http(http, iterations)
    return BenchmarkResult(
        startup_ms=startup_ms,
        dispatch_rps=dispatch_rps,
        http_rps=http_rps,
        iterations=iterations,
        modules=modules,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4 baseline benchmarks.")
    parser.add_argument("--iterations", type=int, default=20_000)
    parser.add_argument("--modules", type=int, default=50)
    args = parser.parse_args()
    result = asyncio.run(run(iterations=args.iterations, modules=args.modules))
    print(json.dumps(result.to_payload(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
