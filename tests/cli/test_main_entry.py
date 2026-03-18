from __future__ import annotations

import builtins
import importlib
import json
import sys
import types
from dataclasses import dataclass

import pytest

cli_main = importlib.import_module("pyferox.cli.main")


def test_main_dispatches_create_project(monkeypatch) -> None:
    seen: dict[str, str] = {}
    monkeypatch.setattr(sys, "argv", ["pyferox", "create-project", "demo"])
    monkeypatch.setattr(
        cli_main,
        "_create_project",
        lambda name, template="api": seen.update({"name": name, "template": template}),
    )
    assert cli_main.main() == 0
    assert seen["name"] == "demo"
    assert seen["template"] == "api"


def test_main_dispatches_create_module(monkeypatch) -> None:
    seen: dict[str, str] = {}
    monkeypatch.setattr(sys, "argv", ["pyferox", "create-module", "users", "--project", "app"])
    monkeypatch.setattr(
        cli_main,
        "_create_module",
        lambda project, name: seen.update({"project": project, "name": name}),
    )
    assert cli_main.main() == 0
    assert seen == {"project": "app", "name": "users"}


def test_main_dispatches_run_dev(monkeypatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        sys,
        "argv",
        ["pyferox", "run-dev", "--target", "demo.main:http", "--host", "0.0.0.0", "--port", "9000"],
    )
    monkeypatch.setattr(
        cli_main,
        "_run_dev",
        lambda target, host="127.0.0.1", port=8000: seen.update({"target": target, "host": host, "port": port}),
    )
    assert cli_main.main() == 0
    assert seen == {"target": "demo.main:http", "host": "0.0.0.0", "port": 9000}


def test_main_dispatches_runserver_alias(monkeypatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pyferox",
            "runserver",
            "--target",
            "demo.main:http",
            "--host",
            "0.0.0.0",
            "--port",
            "9100",
            "--workers",
            "2",
            "--reload",
            "--access-log",
            "--loop",
            "asyncio",
            "--http",
            "h11",
            "--log-level",
            "warning",
        ],
    )
    monkeypatch.setattr(
        cli_main,
        "_run_server",
        lambda target, **kwargs: seen.update({"target": target, **kwargs}),
    )
    assert cli_main.main() == 0
    assert seen == {
        "target": "demo.main:http",
        "host": "0.0.0.0",
        "port": 9100,
        "workers": 2,
        "reload": True,
        "access_log": True,
        "loop": "asyncio",
        "http": "h11",
        "log_level": "warning",
    }


def test_main_dispatches_inspect_config(monkeypatch) -> None:
    seen: dict[str, str | None] = {}
    monkeypatch.setattr(sys, "argv", ["pyferox", "inspect-config", "--profile", "test"])
    monkeypatch.setattr(cli_main, "_inspect_config", lambda profile=None: seen.setdefault("profile", profile))
    assert cli_main.main() == 0
    assert seen["profile"] == "test"


def test_main_returns_non_zero_for_unknown_command(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_main.argparse.ArgumentParser,
        "parse_args",
        lambda self: types.SimpleNamespace(command="unknown"),
    )
    assert cli_main.main() == 1


def test_run_dev_invokes_uvicorn(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    uvicorn_module = types.SimpleNamespace(run=lambda *args, **kwargs: calls.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn_module)
    cli_main._run_dev("demo_target:http", host="0.0.0.0", port=9000)
    assert len(calls) == 1
    assert calls[0]["args"] == ("demo_target:http",)
    assert calls[0]["kwargs"] == {
        "host": "0.0.0.0",
        "port": 9000,
        "reload": True,
        "workers": 1,
        "access_log": True,
        "loop": "auto",
        "http": "auto",
        "log_level": "info",
    }


def test_run_server_invokes_uvicorn_with_runtime_flags(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    uvicorn_module = types.SimpleNamespace(run=lambda *args, **kwargs: calls.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn_module)
    cli_main._run_server(
        "demo_target:http",
        host="127.0.0.1",
        port=8010,
        workers=4,
        reload=False,
        access_log=False,
        loop="uvloop",
        http="httptools",
        log_level="warning",
    )
    assert len(calls) == 1
    assert calls[0]["args"] == ("demo_target:http",)
    assert calls[0]["kwargs"] == {
        "host": "127.0.0.1",
        "port": 8010,
        "reload": False,
        "workers": 4,
        "access_log": False,
        "loop": "uvloop",
        "http": "httptools",
        "log_level": "warning",
    }


def test_run_dev_raises_when_uvicorn_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "uvicorn":
            raise ModuleNotFoundError("missing uvicorn")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError):
        cli_main._run_dev("demo_target:http")


def test_inspect_config_prints_json(monkeypatch, capsys) -> None:
    @dataclass(slots=True)
    class FakeConfig:
        profile: str = "dev"

    monkeypatch.setattr("pyferox.config.load_config", lambda profile=None: FakeConfig(profile="test"))
    cli_main._inspect_config(profile="test")
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["profile"] == "test"


def test_main_dispatches_migration_commands(monkeypatch) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(cli_main, "_run_migration", lambda kind, **kwargs: seen.append((kind, kwargs)))

    monkeypatch.setattr(sys, "argv", ["pyferox", "migrate-init", "--directory", "db/migrations", "--cwd", "."])
    assert cli_main.main() == 0

    monkeypatch.setattr(
        sys,
        "argv",
        ["pyferox", "migrate-revision", "-m", "init", "--autogenerate", "--cwd", "."],
    )
    assert cli_main.main() == 0

    monkeypatch.setattr(sys, "argv", ["pyferox", "migrate-upgrade", "--revision", "head"])
    assert cli_main.main() == 0

    monkeypatch.setattr(sys, "argv", ["pyferox", "migrate-downgrade", "--revision", "-1"])
    assert cli_main.main() == 0

    monkeypatch.setattr(sys, "argv", ["pyferox", "migrate-current"])
    assert cli_main.main() == 0

    assert seen[0][0] == "init"
    assert seen[1][0] == "revision"
    assert seen[2][0] == "upgrade"
    assert seen[3][0] == "downgrade"
    assert seen[4][0] == "current"


def test_main_dispatches_jobs_and_env_diagnostics(monkeypatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(sys, "argv", ["pyferox", "jobs-run", "--target", "demo.jobs:worker", "--idle-rounds", "2"])
    monkeypatch.setattr(
        cli_main,
        "_run_jobs",
        lambda target, idle_rounds=1: seen.update({"target": target, "idle_rounds": idle_rounds}),
    )
    assert cli_main.main() == 0
    assert seen == {"target": "demo.jobs:worker", "idle_rounds": 2}

    monkeypatch.setattr(sys, "argv", ["pyferox", "env-diagnostics"])
    monkeypatch.setattr(cli_main, "_env_diagnostics", lambda: seen.setdefault("env", True))
    assert cli_main.main() == 0
    assert seen["env"] is True


def test_main_dispatches_phase3_runtime_commands(monkeypatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        sys,
        "argv",
        ["pyferox", "worker-run", "--target", "demo.jobs:worker", "--idle-timeout", "0.1", "--max-iterations", "2"],
    )
    monkeypatch.setattr(
        cli_main,
        "_run_worker",
        lambda target, idle_timeout=0.25, max_iterations=0: seen.update(
            {"worker_target": target, "idle_timeout": idle_timeout, "max_iterations": max_iterations}
        ),
    )
    assert cli_main.main() == 0

    monkeypatch.setattr(sys, "argv", ["pyferox", "scheduler-run", "--target", "demo.scheduler:runtime", "--ticks", "3"])
    monkeypatch.setattr(cli_main, "_run_scheduler", lambda target, ticks=1: seen.update({"scheduler_target": target, "ticks": ticks}))
    assert cli_main.main() == 0

    monkeypatch.setattr(sys, "argv", ["pyferox", "health-check", "--target", "demo.health:registry"])
    monkeypatch.setattr(cli_main, "_run_health_check", lambda target: seen.update({"health_target": target}))
    assert cli_main.main() == 0

    monkeypatch.setattr(sys, "argv", ["pyferox", "ops-diagnostics", "--target", "demo.ops:runtime"])
    monkeypatch.setattr(cli_main, "_run_ops_diagnostics", lambda target: seen.update({"ops_target": target}))
    assert cli_main.main() == 0

    assert seen["worker_target"] == "demo.jobs:worker"
    assert seen["max_iterations"] == 2
    assert seen["scheduler_target"] == "demo.scheduler:runtime"
    assert seen["ticks"] == 3
    assert seen["health_target"] == "demo.health:registry"
    assert seen["ops_target"] == "demo.ops:runtime"


def test_run_migration_raises_on_failure(monkeypatch) -> None:
    class Result:
        ok = False
        returncode = 2
        stdout = ""
        stderr = "err"

    monkeypatch.setattr("pyferox.db.migration_upgrade", lambda revision="head", cwd=".": Result())
    with pytest.raises(RuntimeError):
        cli_main._run_migration("upgrade", revision="head", cwd=".")


def test_run_jobs_supports_worker_object(monkeypatch) -> None:
    class Worker:
        def __init__(self) -> None:
            self.called = 0

        async def run_until_idle(self, idle_rounds=1) -> None:
            self.called += idle_rounds

    worker = Worker()
    module = types.ModuleType("demo_jobs")
    module.worker = worker
    monkeypatch.setitem(sys.modules, "demo_jobs", module)

    cli_main._run_jobs("demo_jobs:worker", idle_rounds=3)
    assert worker.called == 3


def test_run_worker_supports_dispatcher_iteration(monkeypatch) -> None:
    class Dispatcher:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self, timeout=0.0) -> None:
            self.calls += 1

    class Worker:
        def __init__(self) -> None:
            self.dispatcher = Dispatcher()

    worker = Worker()
    module = types.ModuleType("demo_worker")
    module.worker = worker
    monkeypatch.setitem(sys.modules, "demo_worker", module)

    cli_main._run_worker("demo_worker:worker", idle_timeout=0.01, max_iterations=2)
    assert worker.dispatcher.calls == 2


def test_run_scheduler_and_health_helpers(monkeypatch, capsys) -> None:
    class Scheduler:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self) -> None:
            self.calls += 1

    scheduler = Scheduler()
    scheduler_module = types.ModuleType("demo_scheduler")
    scheduler_module.runtime = scheduler
    monkeypatch.setitem(sys.modules, "demo_scheduler", scheduler_module)
    cli_main._run_scheduler("demo_scheduler:runtime", ticks=3)
    assert scheduler.calls == 3

    class Ready:
        async def run_readiness(self) -> dict[str, object]:
            return {"ok": True, "service": "up"}

    ready_module = types.ModuleType("demo_health")
    ready_module.registry = Ready()
    monkeypatch.setitem(sys.modules, "demo_health", ready_module)
    cli_main._run_health_check("demo_health:registry")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_run_ops_diagnostics_with_runtime_object(monkeypatch, capsys) -> None:
    class Runtime:
        async def diagnostics(self) -> dict[str, object]:
            return {"ok": True, "workers": 1}

    runtime_module = types.ModuleType("demo_ops")
    runtime_module.runtime = Runtime()
    monkeypatch.setitem(sys.modules, "demo_ops", runtime_module)

    cli_main._run_ops_diagnostics("demo_ops:runtime")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["workers"] == 1


def test_run_jobs_branch_matrix(monkeypatch) -> None:
    from pyferox import App
    from pyferox.jobs import JobDispatcher, LocalJobWorker

    worker_module = types.ModuleType("demo_jobs_worker")
    worker_module.worker = LocalJobWorker(JobDispatcher(App()))
    monkeypatch.setitem(sys.modules, "demo_jobs_worker", worker_module)
    cli_main._run_jobs("demo_jobs_worker:worker", idle_rounds=1)

    sync_module = types.ModuleType("demo_jobs_sync")

    class SyncObj:
        def __init__(self) -> None:
            self.called = 0

        def run_until_idle(self, idle_rounds=1):  # type: ignore[no-untyped-def]
            self.called += idle_rounds
            return None

    sync_obj = SyncObj()
    sync_module.obj = sync_obj
    monkeypatch.setitem(sys.modules, "demo_jobs_sync", sync_module)
    cli_main._run_jobs("demo_jobs_sync:obj", idle_rounds=2)
    assert sync_obj.called == 2

    callable_module = types.ModuleType("demo_jobs_callable")

    class Nested:
        async def run_until_idle(self, idle_rounds=1):  # type: ignore[no-untyped-def]
            return None

    callable_module.factory = lambda: Nested()
    monkeypatch.setitem(sys.modules, "demo_jobs_callable", callable_module)
    cli_main._run_jobs("demo_jobs_callable:factory", idle_rounds=1)

    bad_module = types.ModuleType("demo_jobs_bad")
    bad_module.bad = object()
    monkeypatch.setitem(sys.modules, "demo_jobs_bad", bad_module)
    with pytest.raises(RuntimeError):
        cli_main._run_jobs("demo_jobs_bad:bad", idle_rounds=1)


def test_run_worker_branch_matrix(monkeypatch) -> None:
    sync_dispatch_module = types.ModuleType("demo_worker_sync_dispatch")

    class SyncDispatcher:
        def __init__(self) -> None:
            self.calls = 0

        def run_once(self, timeout=0.0):  # type: ignore[no-untyped-def]
            self.calls += 1

    class SyncDispatchWorker:
        def __init__(self) -> None:
            self.dispatcher = SyncDispatcher()

    worker = SyncDispatchWorker()
    sync_dispatch_module.worker = worker
    monkeypatch.setitem(sys.modules, "demo_worker_sync_dispatch", sync_dispatch_module)
    cli_main._run_worker("demo_worker_sync_dispatch:worker", idle_timeout=0.01, max_iterations=2)
    assert worker.dispatcher.calls == 2

    run_forever_module = types.ModuleType("demo_worker_forever")

    class Forever:
        def __init__(self) -> None:
            self.called = 0

        def run_forever(self, poll_interval=0.0):  # type: ignore[no-untyped-def]
            self.called += 1

    forever = Forever()
    run_forever_module.worker = forever
    monkeypatch.setitem(sys.modules, "demo_worker_forever", run_forever_module)
    cli_main._run_worker("demo_worker_forever:worker", idle_timeout=0.01)
    assert forever.called == 1

    run_module = types.ModuleType("demo_worker_run")

    class Runner:
        def __init__(self) -> None:
            self.called = 0

        def run(self, idle_timeout=0.0):  # type: ignore[no-untyped-def]
            self.called += 1

    runner = Runner()
    run_module.worker = runner
    monkeypatch.setitem(sys.modules, "demo_worker_run", run_module)
    cli_main._run_worker("demo_worker_run:worker", idle_timeout=0.01)
    assert runner.called == 1

    until_idle_module = types.ModuleType("demo_worker_idle")

    class Idle:
        def __init__(self) -> None:
            self.called = 0

        def run_until_idle(self, idle_rounds=1, timeout=0.0):  # type: ignore[no-untyped-def]
            self.called += idle_rounds

    idle = Idle()
    until_idle_module.worker = idle
    monkeypatch.setitem(sys.modules, "demo_worker_idle", until_idle_module)
    cli_main._run_worker("demo_worker_idle:worker", max_iterations=3)
    assert idle.called == 3

    callable_module = types.ModuleType("demo_worker_callable")
    callable_module.factory = lambda: idle
    monkeypatch.setitem(sys.modules, "demo_worker_callable", callable_module)
    cli_main._run_worker("demo_worker_callable:factory", max_iterations=1)

    bad_module = types.ModuleType("demo_worker_bad")
    bad_module.bad = object()
    monkeypatch.setitem(sys.modules, "demo_worker_bad", bad_module)
    with pytest.raises(RuntimeError):
        cli_main._run_worker("demo_worker_bad:bad")


def test_run_scheduler_branch_matrix(monkeypatch) -> None:
    run_once_module = types.ModuleType("demo_sched_once")

    class Once:
        def __init__(self) -> None:
            self.calls = 0

        def run_once(self):  # type: ignore[no-untyped-def]
            self.calls += 1

    once = Once()
    run_once_module.scheduler = once
    monkeypatch.setitem(sys.modules, "demo_sched_once", run_once_module)
    cli_main._run_scheduler("demo_sched_once:scheduler", ticks=2)
    assert once.calls == 2

    run_pending_module = types.ModuleType("demo_sched_pending")

    class Pending:
        def __init__(self) -> None:
            self.calls = 0

        def run_pending(self):  # type: ignore[no-untyped-def]
            self.calls += 1

    pending = Pending()
    run_pending_module.scheduler = pending
    monkeypatch.setitem(sys.modules, "demo_sched_pending", run_pending_module)
    cli_main._run_scheduler("demo_sched_pending:scheduler", ticks=2)
    assert pending.calls == 2

    callable_module = types.ModuleType("demo_sched_callable")
    callable_module.factory = lambda: pending
    monkeypatch.setitem(sys.modules, "demo_sched_callable", callable_module)
    cli_main._run_scheduler("demo_sched_callable:factory", ticks=1)

    bad_module = types.ModuleType("demo_sched_bad")
    bad_module.bad = object()
    monkeypatch.setitem(sys.modules, "demo_sched_bad", bad_module)
    with pytest.raises(RuntimeError):
        cli_main._run_scheduler("demo_sched_bad:bad")


def test_run_health_check_branch_matrix(monkeypatch, capsys) -> None:
    from pyferox.ops import HealthRegistry, HealthReport
    from pyferox.ops.runtime import HealthCheckResult

    registry = HealthRegistry()
    registry.add_readiness("ok", lambda: True)
    module_registry = types.ModuleType("demo_health_registry")
    module_registry.registry = registry
    monkeypatch.setitem(sys.modules, "demo_health_registry", module_registry)
    cli_main._run_health_check("demo_health_registry:registry")
    assert json.loads(capsys.readouterr().out)["ok"] is True

    class ReportObj:
        def to_payload(self) -> dict[str, object]:
            return {"ok": True, "via": "report"}

    module_report = types.ModuleType("demo_health_report")
    module_report.obj = type("Obj", (), {"run_readiness": lambda self: ReportObj()})()
    monkeypatch.setitem(sys.modules, "demo_health_report", module_report)
    cli_main._run_health_check("demo_health_report:obj")

    module_bool = types.ModuleType("demo_health_bool")
    module_bool.obj = type("Obj", (), {"run_readiness": lambda self: False})()
    monkeypatch.setitem(sys.modules, "demo_health_bool", module_bool)
    with pytest.raises(RuntimeError):
        cli_main._run_health_check("demo_health_bool:obj")

    module_callable = types.ModuleType("demo_health_callable")
    module_callable.obj = lambda: {"ok": True}
    monkeypatch.setitem(sys.modules, "demo_health_callable", module_callable)
    cli_main._run_health_check("demo_health_callable:obj")

    module_bad = types.ModuleType("demo_health_bad")
    module_bad.obj = object()
    monkeypatch.setitem(sys.modules, "demo_health_bad", module_bad)
    with pytest.raises(RuntimeError):
        cli_main._run_health_check("demo_health_bad:obj")


def test_run_ops_diagnostics_branch_matrix(monkeypatch, capsys) -> None:
    from pyferox.ops import HealthRegistry, InMemoryTraceCollector

    module_diag_sync = types.ModuleType("demo_ops_sync")
    module_diag_sync.obj = type("Obj", (), {"diagnostics": lambda self: {"ok": True, "x": 1}})()
    monkeypatch.setitem(sys.modules, "demo_ops_sync", module_diag_sync)
    cli_main._run_ops_diagnostics("demo_ops_sync:obj")
    assert json.loads(capsys.readouterr().out)["ok"] is True

    module_callable = types.ModuleType("demo_ops_callable")
    module_callable.obj = lambda: {"ok": True, "y": 2}
    monkeypatch.setitem(sys.modules, "demo_ops_callable", module_callable)
    cli_main._run_ops_diagnostics("demo_ops_callable:obj")

    health = HealthRegistry()
    health.add_liveness("live", lambda: True)
    health.add_readiness("ready", lambda: True)
    trace = InMemoryTraceCollector()
    module_attrs = types.ModuleType("demo_ops_attrs")
    module_attrs.obj = type("Obj", (), {"health_registry": health, "trace_collector": trace})()
    monkeypatch.setitem(sys.modules, "demo_ops_attrs", module_attrs)
    cli_main._run_ops_diagnostics("demo_ops_attrs:obj")

    module_health = types.ModuleType("demo_ops_health")
    module_health.obj = health
    monkeypatch.setitem(sys.modules, "demo_ops_health", module_health)
    cli_main._run_ops_diagnostics("demo_ops_health:obj")

    module_trace = types.ModuleType("demo_ops_trace")
    module_trace.obj = trace
    monkeypatch.setitem(sys.modules, "demo_ops_trace", module_trace)
    cli_main._run_ops_diagnostics("demo_ops_trace:obj")

    module_bad = types.ModuleType("demo_ops_bad")
    module_bad.obj = object()
    monkeypatch.setitem(sys.modules, "demo_ops_bad", module_bad)
    with pytest.raises(RuntimeError):
        cli_main._run_ops_diagnostics("demo_ops_bad:obj")

    module_not_ok = types.ModuleType("demo_ops_not_ok")
    module_not_ok.obj = lambda: {"ok": False}
    monkeypatch.setitem(sys.modules, "demo_ops_not_ok", module_not_ok)
    with pytest.raises(RuntimeError):
        cli_main._run_ops_diagnostics("demo_ops_not_ok:obj")


def test_run_migration_branches_and_unknown(monkeypatch, capsys) -> None:
    class Result:
        def __init__(self, stdout="", stderr="", ok=True, returncode=0) -> None:
            self.stdout = stdout
            self.stderr = stderr
            self.ok = ok
            self.returncode = returncode

    monkeypatch.setattr("pyferox.db.migration_init", lambda directory="migrations", cwd=".": Result(stdout="init"))
    monkeypatch.setattr("pyferox.db.migration_revision", lambda message, autogenerate=False, cwd=".": Result(stdout="rev"))
    monkeypatch.setattr("pyferox.db.migration_downgrade", lambda revision, cwd=".": Result(stderr="warn"))
    monkeypatch.setattr("pyferox.db.migration_current", lambda cwd=".": Result(stdout="cur"))

    cli_main._run_migration("init")
    cli_main._run_migration("revision", message="x")
    cli_main._run_migration("downgrade", revision="-1")
    cli_main._run_migration("current")
    output = capsys.readouterr()
    assert "init" in output.out
    assert "rev" in output.out
    assert "cur" in output.out
    assert "warn" in output.err

    with pytest.raises(RuntimeError):
        cli_main._run_migration("unknown")


def test_env_diagnostics_prints_json(capsys) -> None:
    cli_main._env_diagnostics()
    payload = json.loads(capsys.readouterr().out)
    assert "python_version" in payload
    assert "platform" in payload


def test_run_jobs_async_callable_and_missing_nested_runner_paths(monkeypatch) -> None:
    async_callable_module = types.ModuleType("demo_jobs_async_callable")

    async def async_callable() -> None:
        return None

    async_callable_module.obj = async_callable
    monkeypatch.setitem(sys.modules, "demo_jobs_async_callable", async_callable_module)
    cli_main._run_jobs("demo_jobs_async_callable:obj", idle_rounds=1)

    nested_sync_module = types.ModuleType("demo_jobs_nested_sync")

    class NestedSync:
        def __init__(self) -> None:
            self.called = 0

        def run_until_idle(self, idle_rounds=1):  # type: ignore[no-untyped-def]
            self.called += idle_rounds
            return None

    nested = NestedSync()
    nested_sync_module.obj = lambda: nested
    monkeypatch.setitem(sys.modules, "demo_jobs_nested_sync", nested_sync_module)
    cli_main._run_jobs("demo_jobs_nested_sync:obj", idle_rounds=2)
    assert nested.called == 2

    no_nested_module = types.ModuleType("demo_jobs_no_nested")
    no_nested_module.obj = lambda: object()
    monkeypatch.setitem(sys.modules, "demo_jobs_no_nested", no_nested_module)
    with pytest.raises(RuntimeError):
        cli_main._run_jobs("demo_jobs_no_nested:obj", idle_rounds=1)


def test_run_worker_async_execution_paths(monkeypatch) -> None:
    forever_module = types.ModuleType("demo_worker_async_forever")

    class AsyncForever:
        def __init__(self) -> None:
            self.called = 0

        async def run_forever(self, poll_interval=0.0):  # type: ignore[no-untyped-def]
            self.called += 1

    forever = AsyncForever()
    forever_module.worker = forever
    monkeypatch.setitem(sys.modules, "demo_worker_async_forever", forever_module)
    cli_main._run_worker("demo_worker_async_forever:worker", idle_timeout=0.01)
    assert forever.called == 1

    run_module = types.ModuleType("demo_worker_async_run")

    class AsyncRun:
        def __init__(self) -> None:
            self.called = 0

        async def run(self, idle_timeout=0.0):  # type: ignore[no-untyped-def]
            self.called += 1

    runner = AsyncRun()
    run_module.worker = runner
    monkeypatch.setitem(sys.modules, "demo_worker_async_run", run_module)
    cli_main._run_worker("demo_worker_async_run:worker", idle_timeout=0.01)
    assert runner.called == 1

    idle_module = types.ModuleType("demo_worker_async_idle")

    class AsyncIdle:
        def __init__(self) -> None:
            self.called = 0

        async def run_until_idle(self, idle_rounds=1, timeout=0.0):  # type: ignore[no-untyped-def]
            self.called += idle_rounds

    idle = AsyncIdle()
    idle_module.worker = idle
    monkeypatch.setitem(sys.modules, "demo_worker_async_idle", idle_module)
    cli_main._run_worker("demo_worker_async_idle:worker", max_iterations=2)
    assert idle.called == 2

    callable_module = types.ModuleType("demo_worker_async_callable")

    async def factory() -> AsyncIdle:
        return idle

    callable_module.obj = factory
    monkeypatch.setitem(sys.modules, "demo_worker_async_callable", callable_module)
    cli_main._run_worker("demo_worker_async_callable:obj", max_iterations=1)


def test_run_scheduler_async_branches(monkeypatch) -> None:
    pending_module = types.ModuleType("demo_scheduler_async_pending")

    class AsyncPending:
        def __init__(self) -> None:
            self.calls = 0

        async def run_pending(self):  # type: ignore[no-untyped-def]
            self.calls += 1

    pending = AsyncPending()
    pending_module.scheduler = pending
    monkeypatch.setitem(sys.modules, "demo_scheduler_async_pending", pending_module)
    cli_main._run_scheduler("demo_scheduler_async_pending:scheduler", ticks=2)
    assert pending.calls == 2

    once_module = types.ModuleType("demo_scheduler_async_once")

    class AsyncOnce:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self) -> None:
            self.calls += 1

    once = AsyncOnce()

    async def factory() -> AsyncOnce:
        return once

    once_module.scheduler = factory
    monkeypatch.setitem(sys.modules, "demo_scheduler_async_once", once_module)
    cli_main._run_scheduler("demo_scheduler_async_once:scheduler", ticks=1)
    assert once.calls == 1


def test_run_health_check_async_callable_and_non_dict_result_paths(monkeypatch, capsys) -> None:
    async_module = types.ModuleType("demo_health_async_callable")

    async def async_check() -> dict[str, object]:
        return {"ok": True, "source": "async"}

    async_module.obj = async_check
    monkeypatch.setitem(sys.modules, "demo_health_async_callable", async_module)
    cli_main._run_health_check("demo_health_async_callable:obj")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True

    truthy_module = types.ModuleType("demo_health_truthy")
    truthy_module.obj = lambda: 2
    monkeypatch.setitem(sys.modules, "demo_health_truthy", truthy_module)
    cli_main._run_health_check("demo_health_truthy:obj")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True


def test_run_ops_diagnostics_async_non_dict_fallback_paths(monkeypatch, capsys) -> None:
    from pyferox.ops import HealthRegistry

    health = HealthRegistry()

    class Runtime:
        def __init__(self) -> None:
            self.health_registry = health

        async def diagnostics(self) -> object:
            return "not-a-dict"

        async def __call__(self) -> object:
            return "still-not-a-dict"

    module = types.ModuleType("demo_ops_async_fallback")
    module.runtime = Runtime()
    monkeypatch.setitem(sys.modules, "demo_ops_async_fallback", module)

    cli_main._run_ops_diagnostics("demo_ops_async_fallback:runtime")
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
