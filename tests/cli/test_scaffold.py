from __future__ import annotations

from pathlib import Path

from pyferox.cli.main import _create_module, _create_project


def test_create_project(tmp_path: Path) -> None:
    project_path = tmp_path / "demo"
    _create_project(str(project_path))
    assert (project_path / "app" / "main.py").exists()
    assert (project_path / "app" / "config.py").exists()
    assert (project_path / ".env").exists()
    assert (project_path / ".env.dev").exists()
    assert (project_path / ".env.test").exists()
    assert (project_path / ".env.prod").exists()
    assert (project_path / "app" / "routes.py").exists()
    env_contents = (project_path / ".env").read_text(encoding="utf-8")
    assert "PYFEROX_PROFILE=dev" in env_contents
    assert "# Base environment" in env_contents
    routes_contents = (project_path / "app" / "routes.py").read_text(encoding="utf-8")
    assert 'http.query("GET", "/ping", Ping)' in routes_contents


def test_create_module(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    _create_module(str(project), "users")
    assert (project / "users" / "module.py").exists()


def test_create_project_internal_template(tmp_path: Path) -> None:
    project_path = tmp_path / "internal-demo"
    _create_project(str(project_path), template="internal")
    assert (project_path / "app" / "services.py").exists()
    main_contents = (project_path / "app" / "main.py").read_text(encoding="utf-8")
    assert "internal_module" in main_contents
