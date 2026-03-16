from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyferox.config import ChainedSecretProvider, ConfigProfile, DictSecretProvider, FileSecretProvider, load_config, load_env_file


def test_load_env_file_skips_invalid_lines_and_respects_override(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nBADLINE\nKEY=value\n", encoding="utf-8")
    monkeypatch.delenv("KEY", raising=False)

    load_env_file(str(env_file))
    assert os.getenv("KEY") == "value"

    monkeypatch.setenv("KEY", "existing")
    load_env_file(str(env_file), override=False)
    assert os.getenv("KEY") == "existing"
    load_env_file(str(env_file), override=True)
    assert os.getenv("KEY") == "value"


def test_file_secret_provider_missing_file_returns_none(tmp_path: Path) -> None:
    provider = FileSecretProvider(tmp_path)
    assert provider.get("MISSING") is None


def test_chained_secret_provider_falls_through_to_next_provider(tmp_path: Path) -> None:
    (tmp_path / "SECRET").write_text("from-file", encoding="utf-8")
    provider = ChainedSecretProvider(DictSecretProvider({}), FileSecretProvider(tmp_path))
    assert provider.get("SECRET") == "from-file"


def test_chained_secret_provider_returns_none_when_missing() -> None:
    provider = ChainedSecretProvider(DictSecretProvider({}))
    assert provider.get("MISSING") is None


def test_load_env_file_missing_path_is_noop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    load_env_file(".env.missing")
    assert True


def test_load_config_invalid_bool_raises(monkeypatch) -> None:
    monkeypatch.setenv("PYFEROX_HTTP_DEBUG", "maybe")
    with pytest.raises(ValueError):
        load_config(load_dotenv=False)


def test_load_config_prod_profile_overrides_debug_and_echo(monkeypatch) -> None:
    monkeypatch.setenv("PYFEROX_PROFILE", ConfigProfile.PROD.value)
    monkeypatch.setenv("PYFEROX_DB_ECHO", "1")
    monkeypatch.setenv("PYFEROX_HTTP_DEBUG", "1")
    cfg = load_config(load_dotenv=False)
    assert cfg.profile == ConfigProfile.PROD
    assert cfg.database.echo is False
    assert cfg.http.debug is False
