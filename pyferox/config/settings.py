"""Environment-backed typed settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Protocol


class ConfigProfile(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class SecretProvider(Protocol):
    def get(self, name: str) -> str | None:
        ...


class EnvSecretProvider:
    def get(self, name: str) -> str | None:
        return os.getenv(name)


class DictSecretProvider:
    def __init__(self, secrets: Mapping[str, str]) -> None:
        self._secrets = dict(secrets)

    def get(self, name: str) -> str | None:
        return self._secrets.get(name)


class FileSecretProvider:
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def get(self, name: str) -> str | None:
        path = self._directory / name
        if not path.exists() or not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip()


class ChainedSecretProvider:
    def __init__(self, *providers: SecretProvider) -> None:
        self._providers = providers

    def get(self, name: str) -> str | None:
        for provider in self._providers:
            value = provider.get(name)
            if value is not None:
                return value
        return None


@dataclass(slots=True)
class DatabaseConfig:
    url: str
    echo: bool = False


@dataclass(slots=True)
class HttpConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False


@dataclass(slots=True)
class ModuleConfig:
    values: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(slots=True)
class AppConfig:
    profile: ConfigProfile = ConfigProfile.DEV
    app_name: str = "pyferox-app"
    database: DatabaseConfig = field(default_factory=lambda: DatabaseConfig(url="sqlite+aiosqlite:///./app.db"))
    http: HttpConfig = field(default_factory=HttpConfig)
    modules: dict[str, ModuleConfig] = field(default_factory=dict)
    secret_key: str | None = None


def load_env_file(path: str = ".env", *, override: bool = False) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if override:
            os.environ[key.strip()] = value.strip()
        else:
            os.environ.setdefault(key.strip(), value.strip())


def _parse_bool(raw: str, *, key: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {key}: {raw}")


def _parse_int(raw: str, *, key: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {key}: {raw}") from exc


def _parse_scalar(raw: str) -> str | int | float | bool:
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def load_module_config(env_prefix: str) -> dict[str, ModuleConfig]:
    modules: dict[str, ModuleConfig] = {}
    prefix = f"{env_prefix}MODULE_"
    for key, raw_value in os.environ.items():
        if not key.startswith(prefix):
            continue
        remainder = key[len(prefix) :]
        if "__" not in remainder:
            continue
        module_name, setting_name = remainder.split("__", 1)
        module_key = module_name.strip().lower()
        setting_key = setting_name.strip().lower()
        if not module_key or not setting_key:
            continue
        module_config = modules.setdefault(module_key, ModuleConfig())
        module_config.values[setting_key] = _parse_scalar(raw_value)
    return modules


def load_config(
    *,
    env_prefix: str = "PYFEROX_",
    profile: ConfigProfile | None = None,
    secret_provider: SecretProvider | None = None,
    load_dotenv: bool = True,
) -> AppConfig:
    if load_dotenv:
        load_env_file(".env")
    raw_profile = profile.value if profile is not None else os.getenv(f"{env_prefix}PROFILE", ConfigProfile.DEV.value)
    resolved_profile = ConfigProfile(raw_profile)
    if load_dotenv:
        load_env_file(f".env.{resolved_profile.value}", override=True)

    provider = secret_provider or EnvSecretProvider()

    app_name = os.getenv(f"{env_prefix}APP_NAME", "pyferox-app")
    db_url = os.getenv(f"{env_prefix}DB_URL", "sqlite+aiosqlite:///./app.db")
    db_echo = _parse_bool(os.getenv(f"{env_prefix}DB_ECHO", "0"), key=f"{env_prefix}DB_ECHO")
    http_host = os.getenv(f"{env_prefix}HTTP_HOST", "127.0.0.1")
    http_port = _parse_int(os.getenv(f"{env_prefix}HTTP_PORT", "8000"), key=f"{env_prefix}HTTP_PORT")
    http_debug = _parse_bool(os.getenv(f"{env_prefix}HTTP_DEBUG", "0"), key=f"{env_prefix}HTTP_DEBUG")
    secret_key = provider.get(f"{env_prefix}SECRET_KEY")

    if resolved_profile == ConfigProfile.TEST:
        http_debug = True
    if resolved_profile == ConfigProfile.PROD:
        db_echo = False
        http_debug = False
    modules = load_module_config(env_prefix)

    return AppConfig(
        profile=resolved_profile,
        app_name=app_name,
        database=DatabaseConfig(url=db_url, echo=db_echo),
        http=HttpConfig(host=http_host, port=http_port, debug=http_debug),
        modules=modules,
        secret_key=secret_key,
    )
