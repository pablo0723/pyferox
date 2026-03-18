# HTTP, Auth, OpenAPI

## HTTP Adapter Basics

Create adapter:

```python
from pyferox.http import HTTPAdapter

http = HTTPAdapter(app)
```

Register routes:

```python
http.command("POST", "/users", CreateUser, status_code=201)
http.query("GET", "/users/{user_id}", GetUser)
http.list_query("GET", "/users", ListUsers, max_page_size=200)
```

Route conflicts (`same method + path`) raise `RouteConflictError`.

## Request Binding Rules

Incoming payload is merged from:

1. query params
2. JSON body
3. path params

Then parsed using `parse_input(route.message_type, payload)`.

## List Query Conventions

For `list_query` routes:

- `page` and `page_size` map to `PageParams`
- `sort=-field,name` maps to `sorts: list[SortField]`
- `filter.<key>=value` maps to `filters: dict[...]`

If a handler returns a list in list mode, the adapter wraps it into `Paginated`.

Response headers for paginated responses:

- `x-total-count`
- `x-page`
- `x-page-size`

## Streaming Responses

Return `Streamed` from handlers:

```python
from pyferox.core import Streamed


@handle(DownloadReport)
async def download_report(_: DownloadReport) -> Streamed:
    return Streamed(chunks=iter(["part1,", "part2"]), content_type="text/plain")
```

## Auth and Permissions

Pass optional `auth_backend` and `permission_checker`:

```python
http = HTTPAdapter(app, auth_backend=my_auth_backend, permission_checker=my_permission_checker)
```

Token extraction order:

1. `Authorization: Bearer <token>`
2. `x-session-token` header
3. `session` / `session_id` cookie

Require permission at route registration:

```python
http.query("GET", "/admin", AdminQuery, permission="admin:read")
```

Or on handler via decorator:

```python
from pyferox.auth import requires


@handle(AdminQuery)
@requires("admin:read")
async def admin_query_handler(query: AdminQuery):
    ...
```

If route permission is missing and handler has `@requires`, adapter picks it automatically.

## OpenAPI

Enable endpoint:

```python
http.enable_openapi(path="/openapi.json", title="Service API", version="1.0.0")
```

The adapter generates an OpenAPI 3.0.3 JSON document from registered routes and contract types.

Route metadata support:

```python
http.command(
    "POST",
    "/users",
    CreateUser,
    summary="Create user",
    description="Creates a user in the tenant scope",
    tags=("users",),
)
```

Contract metadata support:

```python
from pyferox.core import StructCommand
from pyferox.schema import schema_metadata


@schema_metadata(title="CreateUser", description="Create user payload")
class CreateUser(StructCommand):
    email: str
    name: str
```

## Health Endpoints

Attach a `HealthRegistry`:

```python
from pyferox.ops import HealthRegistry

registry = HealthRegistry()
registry.add_liveness("runtime", lambda: True)
registry.add_readiness("db", lambda: {"ok": True})
http.enable_health_checks(registry)
```

Default endpoints:

- `GET /health/live`
- `GET /health/ready`

Response code is `200` when healthy and `503` when not healthy.
