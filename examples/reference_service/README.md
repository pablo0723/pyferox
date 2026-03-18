# Reference Service (Phase 4 Validation)

This example is a small multi-module backend used as a Phase 4 validation target.

It includes:

- modular composition (`users`, `billing`)
- typed command/query contracts
- provider-backed in-memory repositories
- HTTP routes through `HTTPAdapter`

## Run

```bash
uvicorn app.main:http --host 127.0.0.1 --port 8000 --reload
```

## Endpoints

- `POST /users` -> create user
- `GET /users/{user_id}` -> fetch user
- `GET /billing/{user_id}/balance` -> fetch user balance
- `GET /openapi.json` -> API spec
