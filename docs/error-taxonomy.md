# Error Taxonomy

This document defines Phase 4 error model expectations across transports.

## Layers

- `Framework errors`: runtime misuse or framework-level failures
- `Validation errors`: schema/input failures
- `Domain errors`: business rule violations
- `Infrastructure errors`: database/network/IO/system failures
- `Transport mapping`: conversion into HTTP/RPC/CLI payloads

## Canonical Exceptions

- `ValidationError`
- `NotFoundError`
- `ConflictError`
- `ForbiddenError`
- `UnauthorizedError`
- `PermissionDeniedError`
- `InfrastructureError`
- `HandlerNotFoundError`

## HTTP Mapping

Default mapping via `map_exception_to_transport`:

- validation -> `400`
- not found -> `404`
- conflict -> `409`
- forbidden/permission denied -> `403`
- unauthorized/auth -> `401`
- infrastructure/framework/internal -> `500`

HTTP adapter behavior:

- includes framework payload shape: `{"type": "...", "error": "..."}`
- includes `request_id` in error payloads when execution context exists

## RPC Mapping

RPC server behavior:

- uses framework mapping for handler/validation/domain failures
- returns `RPCResponse(ok=False, status_code=..., error=payload)`
- includes `request_id` in error payload when available from `RPCRequest.metadata`

Client behavior:

- `client.call(...)` raises `RPCError(status_code, payload)`
- `client.request(...)` returns raw `RPCResponse`

## Extension Rules for Custom Errors

- Derive business exceptions from `DomainError` to get stable transport mapping.
- Use `ValidationError(..., details=...)` for field-level input issues.
- Wrap dependency/IO failures in `InfrastructureError` near the boundary.
- Do not leak raw stack traces to user-facing payloads.

## Correlation Requirements

- Carry `request_id` and `trace_id` through transport metadata when possible.
- Log correlation fields in middleware/hooks for failures and latency analysis.
