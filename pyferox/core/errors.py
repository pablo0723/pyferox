"""Core framework exceptions."""

from __future__ import annotations

from typing import Any


class PyFerOxError(Exception):
    """Base framework error."""


class HandlerNotFoundError(PyFerOxError, LookupError):
    """Raised when no handler exists for a message type."""


class RouteConflictError(PyFerOxError, ValueError):
    """Raised when HTTP route registration collides."""


class ValidationError(PyFerOxError, ValueError):
    """Raised when inbound/outbound data is invalid."""

    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class DomainError(PyFerOxError):
    """Base class for domain/application rule errors."""


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class AuthError(PyFerOxError):
    pass


def map_exception_to_transport(exc: Exception) -> tuple[int, dict[str, Any]]:
    if isinstance(exc, ValidationError):
        return 400, _error_payload("validation_error", str(exc), details=exc.details)
    if isinstance(exc, NotFoundError):
        return 404, _error_payload("not_found", str(exc) or "Not found")
    if isinstance(exc, ConflictError):
        return 409, _error_payload("conflict", str(exc) or "Conflict")
    if isinstance(exc, ForbiddenError):
        return 403, _error_payload("forbidden", str(exc) or "Forbidden")
    if isinstance(exc, AuthError):
        return 401, _error_payload("auth_error", str(exc) or "Unauthorized")
    if isinstance(exc, HandlerNotFoundError):
        return 500, _error_payload("handler_not_found", str(exc))
    if isinstance(exc, PyFerOxError):
        return 500, _error_payload("framework_error", str(exc) or "Framework error")
    return 500, _error_payload("internal_error", "Internal server error")


def _error_payload(error_type: str, message: str, *, details: dict[str, str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": error_type, "error": message}
    if details:
        payload["details"] = details
    return payload
