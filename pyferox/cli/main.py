"""Project scaffolding and dev bootstrap CLI."""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import asdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="pyferox")
    sub = parser.add_subparsers(dest="command", required=True)

    project = sub.add_parser("create-project")
    project.add_argument("name")

    module = sub.add_parser("create-module")
    module.add_argument("name")
    module.add_argument("--project", default="app")

    run_dev = sub.add_parser("run-dev")
    run_dev.add_argument("--target", default="app.main:http")

    inspect_config = sub.add_parser("inspect-config")
    inspect_config.add_argument("--profile", choices=["dev", "test", "prod"], default=None)

    args = parser.parse_args()

    if args.command == "create-project":
        _create_project(args.name)
        return 0
    if args.command == "create-module":
        _create_module(args.project, args.name)
        return 0
    if args.command == "run-dev":
        _run_dev(args.target)
        return 0
    if args.command == "inspect-config":
        _inspect_config(profile=args.profile)
        return 0
    return 1


def _create_project(name: str) -> None:
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
    (root / "README.md").write_text(f"# {name}\n", encoding="utf-8")


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


def _inspect_config(*, profile: str | None = None) -> None:
    from pyferox.config import ConfigProfile, load_config

    resolved_profile = ConfigProfile(profile) if profile is not None else None
    config = load_config(profile=resolved_profile)
    print(json.dumps(asdict(config), indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
