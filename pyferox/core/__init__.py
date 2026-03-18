"""Core primitives for transport-agnostic service applications."""

from pyferox.core.app import App, AppState, LifecycleManager, ProviderRegistry, TransportRegistry
from pyferox.core.context import ExecutionContext
from pyferox.core.di import ResolutionError, Scope, provider, singleton
from pyferox.core.dispatcher import Dispatcher, ExceptionHook, SyncPolicy
from pyferox.core.errors import (
    AuthError,
    ConflictError,
    DomainError,
    ForbiddenError,
    FrameworkError,
    HandlerNotFoundError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
    PyFerOxError,
    RouteConflictError,
    UnauthorizedError,
    ValidationError,
    map_exception_to_transport,
    normalize_execution_exception,
)
from pyferox.core.handlers import handle, listen
from pyferox.core.middleware import Middleware
from pyferox.core.messages import Command, Event, Message, Query, contract, get_contract_metadata
from pyferox.core.module import Module, ModuleDefinition
from pyferox.core.results import Empty, Paginated, Streamed, Success, to_payload

__all__ = [
    "App",
    "AppState",
    "Command",
    "Dispatcher",
    "Empty",
    "Event",
    "Message",
    "AuthError",
    "ConflictError",
    "DomainError",
    "ExceptionHook",
    "ForbiddenError",
    "FrameworkError",
    "ExecutionContext",
    "HandlerNotFoundError",
    "InfrastructureError",
    "LifecycleManager",
    "Middleware",
    "Module",
    "ModuleDefinition",
    "Paginated",
    "PermissionDeniedError",
    "PyFerOxError",
    "ProviderRegistry",
    "Query",
    "ResolutionError",
    "RouteConflictError",
    "NotFoundError",
    "Scope",
    "Success",
    "Streamed",
    "SyncPolicy",
    "TransportRegistry",
    "UnauthorizedError",
    "ValidationError",
    "contract",
    "get_contract_metadata",
    "map_exception_to_transport",
    "normalize_execution_exception",
    "handle",
    "listen",
    "provider",
    "singleton",
    "to_payload",
]
