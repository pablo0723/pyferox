# Reference Application Validation

Phase 4 requires validating framework ergonomics on a real multi-module service.

Repository reference app:

- `examples/reference_service/`

## Validation Goals

- module composition clarity (`users`, `billing`)
- handler/provider ergonomics in non-trivial structure
- HTTP route registration conventions
- OpenAPI generation consistency
- local development workflow (`uvicorn app.main:http`)

## Suggested Validation Checklist

- Add a real persistence backend (replace in-memory repos).
- Add auth/permissions on selected routes.
- Add background jobs for async workflows (notifications/invoice processing).
- Add integration tests for module boundaries and lifecycle.
- Capture pain points and feed them into architecture cleanup backlog.

## Why This Exists

This app is intentionally small, but it exercises the same framework surfaces users rely on in production:

- `App`, `Module`, handlers, DI providers
- `HTTPAdapter` command/query mapping
- structured contracts (`StructCommand`, `StructQuery`)
