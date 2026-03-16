from __future__ import annotations

from pathlib import Path

import pytest

from pyferox.config import ChainedSecretProvider, ConfigProfile, DictSecretProvider, FileSecretProvider, load_config


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


def test_load_config_reads_secret_from_custom_provider() -> None:
    cfg = load_config(load_dotenv=False, secret_provider=DictSecretProvider({"PYFEROX_SECRET_KEY": "secret-1"}))
    assert cfg.secret_key == "secret-1"


def test_file_secret_provider_reads_from_directory(tmp_path: Path) -> None:
    (tmp_path / "PYFEROX_SECRET_KEY").write_text("from-file\n", encoding="utf-8")
    provider = FileSecretProvider(tmp_path)
    cfg = load_config(load_dotenv=False, secret_provider=provider)
    assert cfg.secret_key == "from-file"


def test_chained_secret_provider_uses_first_match(tmp_path: Path) -> None:
    (tmp_path / "PYFEROX_SECRET_KEY").write_text("file-value\n", encoding="utf-8")
    provider = ChainedSecretProvider(
        DictSecretProvider({"PYFEROX_SECRET_KEY": "dict-value"}),
        FileSecretProvider(tmp_path),
    )
    cfg = load_config(load_dotenv=False, secret_provider=provider)
    assert cfg.secret_key == "dict-value"
