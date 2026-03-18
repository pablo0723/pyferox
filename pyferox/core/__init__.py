"""Core primitives for transport-agnostic service applications."""

# App runtime
from pyferox.core.app import App, AppState, LifecycleManager, ProviderRegistry, TransportRegistry
from pyferox.core.context import ExecutionContext

# Contracts and messaging
from pyferox.core.messages import (
    Command,
    Event,
    Message,
    Query,
    StructCommand,
    StructEvent,
    StructQuery,
    contract,
    get_contract_metadata,
)
from pyferox.core.pagination import ListQuery, PageParams, SortDirection, SortField, build_page_params, parse_sort

# Dispatch, middleware, handlers, DI
from pyferox.core.di import ResolutionError, Scope, provider, singleton
from pyferox.core.dispatcher import Dispatcher, ExceptionHook, SyncPolicy
from pyferox.core.handlers import handle, listen
from pyferox.core.middleware import Middleware

# Modules
from pyferox.core.module import Module, ModuleDefinition, as_module, module_diagnostics

# Results and errors
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
from pyferox.core.results import Empty, Paginated, Response, Streamed, Success, to_payload

__all__ = [
    # Runtime
    "App",
    "AppState",
    "ExecutionContext",
    "LifecycleManager",
    "ProviderRegistry",
    "TransportRegistry",
    # Contracts
    "Command",
    "Event",
    "ListQuery",
    "Message",
    "PageParams",
    "Query",
    "StructCommand",
    "StructEvent",
    "StructQuery",
    "SortDirection",
    "SortField",
    "build_page_params",
    "contract",
    "get_contract_metadata",
    "parse_sort",
    # Dispatch and DI
    "Dispatcher",
    "ExceptionHook",
    "Middleware",
    "ResolutionError",
    "Scope",
    "SyncPolicy",
    "handle",
    "listen",
    "provider",
    "singleton",
    # Modules
    "Module",
    "ModuleDefinition",
    "as_module",
    "module_diagnostics",
    # Results and errors
    "AuthError",
    "ConflictError",
    "DomainError",
    "Empty",
    "ForbiddenError",
    "FrameworkError",
    "HandlerNotFoundError",
    "InfrastructureError",
    "NotFoundError",
    "Paginated",
    "PermissionDeniedError",
    "PyFerOxError",
    "Response",
    "RouteConflictError",
    "Streamed",
    "Success",
    "UnauthorizedError",
    "ValidationError",
    "map_exception_to_transport",
    "normalize_execution_exception",
    "to_payload",
]
