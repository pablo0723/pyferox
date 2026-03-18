# Testing

PyFerOx includes lightweight test helpers for app, dispatch, and HTTP-level tests.

## Build Test App and Module

```python
from pyferox.testing import create_test_app, create_test_module

app = create_test_app(modules=[
    create_test_module(name="users", handlers=[create_user, get_user], providers=[...]),
])
```

These helpers are thin wrappers around `App` and `Module`.

## HTTP Tests with TestHTTPClient

```python
from pyferox.testing import TestHTTPClient

client = TestHTTPClient(app)
client.command("POST", "/users", CreateUser, status_code=201)
client.query("GET", "/users/{user_id}", GetUser)

response = client.request("POST", "/users", body={"email": "a@example.com", "name": "Ann"})
assert response["status"] == 201
```

Returned payload:

- `status`: HTTP status code
- `json`: parsed JSON body (or `None`)

## Override Dependencies in Tests

Use context manager `override_dependencies`:

```python
from pyferox.core import provider
from pyferox.testing import override_dependencies

with override_dependencies(app, provider(UserRepo, lambda: FakeUserRepo())):
    response = client.request("GET", "/users/1")
```

Providers/singletons are restored automatically when exiting the context.

## Fake Dispatcher for Isolated Tests

```python
from pyferox.testing import FakeDispatcher

fake = FakeDispatcher()
fake.responses[GetUser] = {"id": 1}
```

Useful when you want to isolate transport behavior from business execution.

## Recommended Test Layers

- Unit tests:
  - handlers with fake dependencies
  - middleware and hook behavior
  - retry/idempotency policies
- Integration tests:
  - app + module composition
  - HTTP adapter with route bindings
  - SQLAlchemy module with real async sqlite
- Runtime tests:
  - job dispatcher retry paths
  - scheduler and workflow failure/compensation paths
  - RPC and event dispatch behavior

## Running Tests

```bash
pytest
```

Branch coverage:

```bash
pytest --cov=pyferox --cov-branch
```
