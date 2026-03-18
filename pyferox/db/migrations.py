"""Alembic wrapper utilities for framework CLI integration."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class MigrationResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_alembic(args: list[str], *, cwd: str | Path | None = None) -> MigrationResult:
    executable = shutil.which("alembic")
    if executable is None:
        raise RuntimeError("alembic is required for migration commands")
    completed = subprocess.run(
        [executable, *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    return MigrationResult(
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def migration_init(*, directory: str = "migrations", cwd: str | Path | None = None) -> MigrationResult:
    return run_alembic(["init", directory], cwd=cwd)


def migration_revision(
    *,
    message: str,
    autogenerate: bool = False,
    cwd: str | Path | None = None,
) -> MigrationResult:
    args = ["revision", "-m", message]
    if autogenerate:
        args.append("--autogenerate")
    return run_alembic(args, cwd=cwd)


def migration_upgrade(*, revision: str = "head", cwd: str | Path | None = None) -> MigrationResult:
    return run_alembic(["upgrade", revision], cwd=cwd)


def migration_downgrade(*, revision: str, cwd: str | Path | None = None) -> MigrationResult:
    return run_alembic(["downgrade", revision], cwd=cwd)


def migration_current(*, cwd: str | Path | None = None) -> MigrationResult:
    return run_alembic(["current"], cwd=cwd)

