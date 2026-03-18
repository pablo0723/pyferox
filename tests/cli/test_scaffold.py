from __future__ import annotations

from pathlib import Path

from pyferox.cli.main import _create_module, _create_project


def test_create_project(tmp_path: Path) -> None:
    project_path = tmp_path / "demo"
    _create_project(str(project_path))
    assert (project_path / "app" / "main.py").exists()
    assert (project_path / "app" / "config.py").exists()
    assert (project_path / ".env").exists()
    assert (project_path / "app" / "routes.py").exists()


def test_create_module(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    _create_module(str(project), "users")
    assert (project / "users" / "module.py").exists()


def test_create_project_internal_template(tmp_path: Path) -> None:
    project_path = tmp_path / "internal-demo"
    _create_project(str(project_path), template="internal")
    assert (project_path / "app" / "services.py").exists()
