"""Core primitives for transport-agnostic service applications."""

from pyferox.core.app import App
from pyferox.core.context import ExecutionContext
from pyferox.core.di import ResolutionError, Scope, provider, singleton
from pyferox.core.dispatcher import Dispatcher, SyncPolicy
from pyferox.core.errors import (
    AuthError,
    ConflictError,
    DomainError,
    ForbiddenError,
    HandlerNotFoundError,
    NotFoundError,
    PyFerOxError,
    RouteConflictError,
    ValidationError,
    map_exception_to_transport,
)
from pyferox.core.handlers import handle, listen
from pyferox.core.middleware import Middleware
from pyferox.core.messages import Command, Event, Query
from pyferox.core.module import Module
from pyferox.core.results import Empty, Paginated, Streamed, Success, to_payload

__all__ = [
    "App",
    "Command",
    "Dispatcher",
    "Empty",
    "Event",
    "AuthError",
    "ConflictError",
    "DomainError",
    "ForbiddenError",
    "ExecutionContext",
    "HandlerNotFoundError",
    "Middleware",
    "Module",
    "Paginated",
    "PyFerOxError",
    "Query",
    "ResolutionError",
    "RouteConflictError",
    "NotFoundError",
    "Scope",
    "Success",
    "Streamed",
    "SyncPolicy",
    "ValidationError",
    "map_exception_to_transport",
    "handle",
    "listen",
    "provider",
    "singleton",
    "to_payload",
]
