# CLI Reference

CLI entrypoint: `pyferox`

## Scaffolding

Create project:

```bash
pyferox create-project my_service --template api
pyferox create-project my_internal --template internal
```

`create-project` now generates a richer starter layout:

- `app/config.py` with typed config loader helper
- `.env`, `.env.dev`, `.env.test`, `.env.prod` with commented configuration examples
- template-specific starter modules (`app/routes.py` or `app/services.py`)

Create module:

```bash
pyferox create-module users --project app
```

## App Runtime

Run dev server:

```bash
pyferox run-dev --target app.main:http
pyferox runserver --target app.main:http
```

`--target` format: `<module_path>:<object_name>`

## Config

```bash
pyferox inspect-config
pyferox inspect-config --profile dev
pyferox inspect-config --profile test
pyferox inspect-config --profile prod
```

## Database Migrations

```bash
pyferox migrate-init --directory migrations --cwd .
pyferox migrate-revision -m "create users" --autogenerate --cwd .
pyferox migrate-upgrade --revision head --cwd .
pyferox migrate-downgrade --revision -1 --cwd .
pyferox migrate-current --cwd .
```

These commands call Alembic underneath and fail when Alembic exits non-zero.

## Jobs and Worker

Run a job worker to idle:

```bash
pyferox jobs-run --target app.jobs:worker --idle-rounds 2
```

Run worker runtime:

```bash
pyferox worker-run --target app.jobs:worker --idle-timeout 0.25 --max-iterations 100
```

Accepted worker targets:

- object with `dispatcher.run_once(...)`
- object with `run_forever(...)`
- object with `run(...)`
- object with `run_until_idle(...)`
- callable returning one of the above

## Scheduler

```bash
pyferox scheduler-run --target app.scheduler:runtime --ticks 5
```

Accepted scheduler target:

- object with `run_once()` or `run_pending()`
- callable returning one of these

## Health and Diagnostics

```bash
pyferox health-check --target app.ops:health_registry
pyferox ops-diagnostics --target app.ops:runtime
pyferox env-diagnostics
```

`health-check` exits with error if payload `ok` is false.

`ops-diagnostics` exits with error if payload `ok` is false.

## Troubleshooting Targets

- Ensure target module is importable from current working directory.
- Ensure target object name is correct.
- For dev server, ensure `uvicorn` is installed (`pip install -e ".[http]"`).
- For migrations, ensure `alembic` executable is available in PATH.
