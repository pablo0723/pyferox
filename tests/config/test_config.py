from __future__ import annotations

from pathlib import Path

import pytest

from pyferox.config import ConfigProfile, load_config


def test_load_config_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("PYFEROX_PROFILE", "test")
    monkeypatch.setenv("PYFEROX_APP_NAME", "demo")
    monkeypatch.setenv("PYFEROX_DB_URL", "sqlite+aiosqlite:///./test.db")
    monkeypatch.setenv("PYFEROX_HTTP_PORT", "9000")

    cfg = load_config(load_dotenv=False)
    assert cfg.profile == ConfigProfile.TEST
    assert cfg.app_name == "demo"
    assert cfg.database.url.endswith("test.db")
    assert cfg.http.port == 9000
    assert cfg.http.debug is True


def test_load_config_reads_profile_env_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("PYFEROX_PROFILE=test\nPYFEROX_HTTP_PORT=1000\n", encoding="utf-8")
    (tmp_path / ".env.test").write_text("PYFEROX_HTTP_PORT=7777\n", encoding="utf-8")
    cfg = load_config()
    assert cfg.profile == ConfigProfile.TEST
    assert cfg.http.port == 7777


def test_load_config_invalid_type_raises(monkeypatch) -> None:
    monkeypatch.setenv("PYFEROX_HTTP_PORT", "not-a-port")
    with pytest.raises(ValueError):
        load_config(load_dotenv=False)
