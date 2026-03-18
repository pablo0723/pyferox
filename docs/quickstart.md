# Quickstart

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,http]"
```

`http` extra installs `uvicorn` for ASGI serving.

## 2. Scaffold a Project (Optional)

```bash
pyferox create-project demo_service --template api
cd demo_service
```

This creates:

- `app/main.py` with `App` + `HTTPAdapter`
- `app/config.py` with `load_config()`
- `.env` with `PYFEROX_PROFILE=dev`

## 3. Build a Minimal App

Create `app/main.py`:

```python
from pyferox import App, HTTPAdapter, Module, StructCommand, StructQuery, handle, singleton


class UserRepo:
    def __init__(self) -> None:
        self._rows: dict[int, dict[str, str]] = {}
        self._next = 1

    async def create(self, email: str, name: str) -> int:
        user_id = self._next
        self._next += 1
        self._rows[user_id] = {"email": email, "name": name}
        return user_id

    async def get(self, user_id: int) -> dict[str, str]:
        return self._rows[user_id]


class CreateUser(StructCommand):
    email: str
    name: str


class GetUser(StructQuery):
    user_id: int


@handle(CreateUser)
async def create_user(cmd: CreateUser, users: UserRepo) -> dict[str, int]:
    return {"id": await users.create(cmd.email, cmd.name)}


@handle(GetUser)
async def get_user(query: GetUser, users: UserRepo) -> dict[str, str]:
    return await users.get(query.user_id)


app = App(modules=[Module(handlers=[create_user, get_user], providers=[singleton(UserRepo())])])
http = HTTPAdapter(app)
http.command("POST", "/users", CreateUser, status_code=201)
http.query("GET", "/users/{user_id}", GetUser)
http.enable_openapi(path="/openapi.json", title="Demo Service", version="0.1.0")
```

This is the recommended contract style for new code: `StructCommand` / `StructQuery` / `StructEvent`. They are framework-owned msgspec-backed bases, so users do not need to spell out multiple inheritance in every contract.

## 4. Run

```bash
uvicorn app.main:http --reload
```

## 5. Try It

```bash
curl -X POST http://127.0.0.1:8000/users \
  -H 'content-type: application/json' \
  -d '{"email":"ann@example.com","name":"Ann"}'
```

```bash
curl http://127.0.0.1:8000/users/1
```

```bash
curl http://127.0.0.1:8000/openapi.json
```

## 6. Run Tests

```bash
pytest
```

For more complete coverage checks:

```bash
pytest --cov=pyferox --cov-branch
```
