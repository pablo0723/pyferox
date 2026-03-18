"""Project scaffolding and dev bootstrap CLI."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import os
import platform
import sys
from dataclasses import asdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="pyferox")
    sub = parser.add_subparsers(dest="command", required=True)

    project = sub.add_parser("create-project")
    project.add_argument("name")
    project.add_argument("--template", choices=["api", "internal"], default="api")

    module = sub.add_parser("create-module")
    module.add_argument("name")
    module.add_argument("--project", default="app")

    run_dev = sub.add_parser("run-dev")
    run_dev.add_argument("--target", default="app.main:http")

    run_server = sub.add_parser("runserver")
    run_server.add_argument("--target", default="app.main:http")

    inspect_config = sub.add_parser("inspect-config")
    inspect_config.add_argument("--profile", choices=["dev", "test", "prod"], default=None)

    migrate_init = sub.add_parser("migrate-init")
    migrate_init.add_argument("--directory", default="migrations")
    migrate_init.add_argument("--cwd", default=".")

    migrate_revision = sub.add_parser("migrate-revision")
    migrate_revision.add_argument("-m", "--message", required=True)
    migrate_revision.add_argument("--autogenerate", action="store_true")
    migrate_revision.add_argument("--cwd", default=".")

    migrate_upgrade = sub.add_parser("migrate-upgrade")
    migrate_upgrade.add_argument("--revision", default="head")
    migrate_upgrade.add_argument("--cwd", default=".")

    migrate_downgrade = sub.add_parser("migrate-downgrade")
    migrate_downgrade.add_argument("--revision", required=True)
    migrate_downgrade.add_argument("--cwd", default=".")

    migrate_current = sub.add_parser("migrate-current")
    migrate_current.add_argument("--cwd", default=".")

    jobs_run = sub.add_parser("jobs-run")
    jobs_run.add_argument("--target", required=True)
    jobs_run.add_argument("--idle-rounds", type=int, default=1)

    sub.add_parser("env-diagnostics")

    args = parser.parse_args()

    if args.command == "create-project":
        _create_project(args.name, template=args.template)
        return 0
    if args.command == "create-module":
        _create_module(args.project, args.name)
        return 0
    if args.command == "run-dev":
        _run_dev(args.target)
        return 0
    if args.command == "runserver":
        _run_dev(args.target)
        return 0
    if args.command == "inspect-config":
        _inspect_config(profile=args.profile)
        return 0
    if args.command == "migrate-init":
        _run_migration("init", directory=args.directory, cwd=args.cwd)
        return 0
    if args.command == "migrate-revision":
        _run_migration("revision", message=args.message, autogenerate=args.autogenerate, cwd=args.cwd)
        return 0
    if args.command == "migrate-upgrade":
        _run_migration("upgrade", revision=args.revision, cwd=args.cwd)
        return 0
    if args.command == "migrate-downgrade":
        _run_migration("downgrade", revision=args.revision, cwd=args.cwd)
        return 0
    if args.command == "migrate-current":
        _run_migration("current", cwd=args.cwd)
        return 0
    if args.command == "jobs-run":
        _run_jobs(args.target, idle_rounds=args.idle_rounds)
        return 0
    if args.command == "env-diagnostics":
        _env_diagnostics()
        return 0
    return 1


def _create_project(name: str, *, template: str = "api") -> None:
    root = Path(name)
    root.mkdir(parents=True, exist_ok=True)
    (root / "app").mkdir(exist_ok=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "config.py").write_text(
        "from pyferox.config import load_config\n\nconfig = load_config()\n",
        encoding="utf-8",
    )
    (root / "app" / "main.py").write_text(
        "from pyferox import App\nfrom pyferox.http import HTTPAdapter\n\nfrom app.config import config\n\napp = App()\nhttp = HTTPAdapter(app)\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("PYFEROX_PROFILE=dev\n", encoding="utf-8")
    if template == "api":
        (root / "app" / "routes.py").write_text(
            "from pyferox import HTTPAdapter\n\n\ndef register_routes(http: HTTPAdapter) -> None:\n    pass\n",
            encoding="utf-8",
        )
    if template == "internal":
        (root / "app" / "services.py").write_text(
            "from pyferox import Command\n\n\nclass Healthcheck(Command):\n    pass\n",
            encoding="utf-8",
        )
    (root / "README.md").write_text(f"# {name}\n\nTemplate: {template}\n", encoding="utf-8")


def _create_module(project: str, name: str) -> None:
    module_dir = Path(project) / name
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "module.py").write_text(
        "from pyferox import Module\n\nmodule = Module(name='" + name + "')\n",
        encoding="utf-8",
    )


def _run_dev(target: str) -> None:
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - optional runtime
        raise RuntimeError("uvicorn is required for run-dev") from exc

    module_name, obj_name = target.split(":", 1)
    module = importlib.import_module(module_name)
    app = getattr(module, obj_name)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)


def _import_target(target: str) -> object:
    module_name, obj_name = target.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, obj_name)


def _run_jobs(target: str, *, idle_rounds: int = 1) -> None:
    from pyferox.jobs import LocalJobWorker

    target_obj = _import_target(target)

    async def run_obj(obj: object) -> None:
        if isinstance(obj, LocalJobWorker):
            await obj.run_until_idle(idle_rounds=idle_rounds)
            return
        run_until_idle = getattr(obj, "run_until_idle", None)
        if callable(run_until_idle):
            result = run_until_idle(idle_rounds=idle_rounds)
            if inspect.isawaitable(result):
                await result
            return
        if callable(obj):
            result = obj()
            if inspect.isawaitable(result):
                await result
                return
            nested = getattr(result, "run_until_idle", None)
            if callable(nested):
                nested_result = nested(idle_rounds=idle_rounds)
                if inspect.isawaitable(nested_result):
                    await nested_result
                return
        raise RuntimeError("jobs-run target must be a LocalJobWorker, async callable, or object with run_until_idle()")

    asyncio.run(run_obj(target_obj))


def _inspect_config(*, profile: str | None = None) -> None:
    from pyferox.config import ConfigProfile, load_config

    resolved_profile = ConfigProfile(profile) if profile is not None else None
    config = load_config(profile=resolved_profile)
    print(json.dumps(asdict(config), indent=2, sort_keys=True))


def _run_migration(kind: str, **kwargs: object) -> None:
    from pyferox.db import (
        migration_current,
        migration_downgrade,
        migration_init,
        migration_revision,
        migration_upgrade,
    )

    if kind == "init":
        result = migration_init(directory=str(kwargs.get("directory", "migrations")), cwd=str(kwargs.get("cwd", ".")))
    elif kind == "revision":
        result = migration_revision(
            message=str(kwargs["message"]),
            autogenerate=bool(kwargs.get("autogenerate", False)),
            cwd=str(kwargs.get("cwd", ".")),
        )
    elif kind == "upgrade":
        result = migration_upgrade(revision=str(kwargs.get("revision", "head")), cwd=str(kwargs.get("cwd", ".")))
    elif kind == "downgrade":
        result = migration_downgrade(revision=str(kwargs["revision"]), cwd=str(kwargs.get("cwd", ".")))
    elif kind == "current":
        result = migration_current(cwd=str(kwargs.get("cwd", ".")))
    else:
        raise RuntimeError(f"Unknown migration command: {kind}")

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if not result.ok:
        raise RuntimeError(f"Migration command failed with exit code {result.returncode}")


def _env_diagnostics() -> None:
    payload = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "venv": os.getenv("VIRTUAL_ENV"),
        "pyferox_profile": os.getenv("PYFEROX_PROFILE"),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
