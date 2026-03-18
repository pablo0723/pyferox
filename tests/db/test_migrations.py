from __future__ import annotations

import types

import pytest

from pyferox.db import migration_current, migration_downgrade, migration_init, migration_revision, migration_upgrade
from pyferox.db import migrations as migration_module


def test_run_alembic_requires_binary(monkeypatch) -> None:
    monkeypatch.setattr(migration_module.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError):
        migration_module.run_alembic(["current"])


def test_migration_helpers_delegate_to_alembic(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None, capture_output=True, text=True, check=False):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(migration_module.shutil, "which", lambda _: "/usr/bin/alembic")
    monkeypatch.setattr(migration_module.subprocess, "run", fake_run)

    assert migration_init().ok is True
    assert migration_revision(message="init", autogenerate=True).ok is True
    assert migration_upgrade().ok is True
    assert migration_downgrade(revision="-1").ok is True
    assert migration_current().ok is True

    assert calls[0][:2] == ["/usr/bin/alembic", "init"]
    assert calls[1][:4] == ["/usr/bin/alembic", "revision", "-m", "init"]
    assert "--autogenerate" in calls[1]
    assert calls[2] == ["/usr/bin/alembic", "upgrade", "head"]
    assert calls[3] == ["/usr/bin/alembic", "downgrade", "-1"]
    assert calls[4] == ["/usr/bin/alembic", "current"]

