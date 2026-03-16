from __future__ import annotations

import builtins
import importlib
import sys
import types

import pytest

cli_main = importlib.import_module("pyferox.cli.main")


def test_main_dispatches_create_project(monkeypatch) -> None:
    seen: dict[str, str] = {}
    monkeypatch.setattr(sys, "argv", ["pyferox", "create-project", "demo"])
    monkeypatch.setattr(cli_main, "_create_project", lambda name: seen.setdefault("name", name))
    assert cli_main.main() == 0
    assert seen["name"] == "demo"


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
