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
    seen: dict[str, str] = {}
    monkeypatch.setattr(sys, "argv", ["pyferox", "run-dev", "--target", "demo.main:http"])
    monkeypatch.setattr(cli_main, "_run_dev", lambda target: seen.setdefault("target", target))
    assert cli_main.main() == 0
    assert seen["target"] == "demo.main:http"


def test_main_dispatches_runserver_alias(monkeypatch) -> None:
    seen: dict[str, str] = {}
    monkeypatch.setattr(sys, "argv", ["pyferox", "runserver", "--target", "demo.main:http"])
    monkeypatch.setattr(cli_main, "_run_dev", lambda target: seen.setdefault("target", target))
    assert cli_main.main() == 0
    assert seen["target"] == "demo.main:http"


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
    target_module = types.ModuleType("demo_target")
    target_module.http = object()
    calls: list[tuple[object, str, int, bool]] = []
    uvicorn_module = types.SimpleNamespace(
        run=lambda app, host, port, reload: calls.append((app, host, port, reload))
    )

    monkeypatch.setitem(sys.modules, "demo_target", target_module)
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn_module)
    cli_main._run_dev("demo_target:http")
    assert calls == [(target_module.http, "127.0.0.1", 8000, True)]


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


def test_env_diagnostics_prints_json(capsys) -> None:
    cli_main._env_diagnostics()
    payload = json.loads(capsys.readouterr().out)
    assert "python_version" in payload
    assert "platform" in payload
