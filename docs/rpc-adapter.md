# RPC Adapter

PyFerOx RPC is built from three parts:

- `RPCServer`: maps RPC methods to message contracts and dispatches through `App`
- `RPCClient`: calls methods through a transport and raises `RPCError` on failure
- `RPCTransport`: protocol your adapter implements (`send(service, request) -> RPCResponse`)

## Core Types

- `RPCRequest`
  - `method`: method name (for example, `"users.get"`)
  - `payload`: request body
  - `metadata`: transport metadata (`request_id`, `trace_id`, custom keys)
  - `timeout_seconds`: optional per-request timeout
  - `idempotency_key`: optional duplicate-suppression key
  - `idempotency_ttl_seconds`: optional idempotency reservation TTL
- `RPCResponse`
  - `ok`: success flag
  - `status_code`: transport-friendly status code
  - `data`: successful response payload
  - `error`: error payload when `ok=False`

## Quick Start

Server side:

```python
from pyferox.core import App, Module, StructQuery, handle
from pyferox.rpc import RPCServer, InMemoryRPCTransport
from pyferox.reliability import InMemoryIdempotencyStore


class GetUser(StructQuery):
    user_id: int


@handle(GetUser)
async def get_user(query: GetUser) -> dict[str, int]:
    return {"user_id": query.user_id}


app = App(modules=[Module(handlers=[get_user])])
server = RPCServer(app, idempotency_store=InMemoryIdempotencyStore())
server.register("users.get", GetUser)

transport = InMemoryRPCTransport(default_timeout_seconds=5.0)
transport.register_service("users", server)
```

Client side:

```python
from pyferox.rpc import RPCClient
from pyferox.reliability import RetryPolicy

client = RPCClient(
    transport=transport,
    service="users",
    retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.05),
)

result = await client.call(
    "users.get",
    {"user_id": 42},
    timeout_seconds=1.0,
    metadata={"request_id": "req-1", "trace_id": "trace-1"},
    idempotency_key="users.get:42",
)
```

## Building a Custom RPC Adapter

Implement `RPCTransport`:

```python
from pyferox.rpc import RPCRequest, RPCResponse


class MyRPCTransport:
    async def send(self, service: str, request: RPCRequest) -> RPCResponse:
        # 1) encode request
        # 2) send over network/broker
        # 3) decode response
        # 4) map remote/protocol errors to RPCResponse(ok=False, ...)
        ...
```

Guidelines:

- Keep wire payload shape stable (`method`, `payload`, `metadata`, timeout/idempotency fields).
- Return structured failures with `error={"type": "...", "error": "..."}`.
- Respect `request.timeout_seconds` when the transport can enforce it.
- Preserve `metadata` to support request/trace correlation.

## Timeouts and Retries

- `InMemoryRPCTransport(default_timeout_seconds=...)` enforces a default timeout.
- `RPCRequest.timeout_seconds` overrides transport default for a single call.
- `RPCClient` retries failed requests using `RetryPolicy` + retry classifier.

When retries are enabled, prefer idempotent handlers or pass an `idempotency_key`.

## Idempotency

`RPCServer(..., idempotency_store=...)` supports duplicate suppression:

- completed key returns cached success result
- in-flight key returns `409` conflict
- failed execution is marked failed in the store

Use stable business keys, for example:

- `"users.get:42"` for read calls
- `"payments.charge:{order_id}"` for write calls

## Error Handling

- `client.call(...)` returns `data` on success.
- `client.call(...)` raises `RPCError` on non-OK response.
- `client.request(...)` returns raw `RPCResponse` when you want to branch manually.

Server-side exceptions are mapped through framework transport mapping, so domain/validation errors remain structured.

## Testing

- Use `InMemoryRPCTransport` for unit/integration tests.
- Register a real `RPCServer` against an app module and call with `RPCClient`.
- Test timeout (`504`), method-not-found (`404`), and idempotency conflict (`409`) paths.
