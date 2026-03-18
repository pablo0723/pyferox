"""PyFerOx service framework public API."""

# Package namespaces (discoverable grouped imports)
from pyferox import auth, cache, config, core, db, http, jobs, schema, testing

# Core runtime and composition
from pyferox.core import (
    App,
    AppState,
    ExecutionContext,
    LifecycleManager,
    Module,
    ModuleDefinition,
    ProviderRegistry,
    TransportRegistry,
    module_diagnostics,
)

# Messaging and handler contracts
from pyferox.core import (
    Command,
    Event,
    ListQuery,
    Message,
    PageParams,
    Query,
    SortDirection,
    SortField,
    build_page_params,
    contract,
    get_contract_metadata,
    parse_sort,
)

# Dispatch, middleware, dependency injection
from pyferox.core import (
    Dispatcher,
    ExceptionHook,
    Middleware,
    ResolutionError,
    Scope,
    SyncPolicy,
    handle,
    listen,
    provider,
    singleton,
)

# Results, errors, transport mapping
from pyferox.core import (
    AuthError,
    ConflictError,
    DomainError,
    Empty,
    ForbiddenError,
    FrameworkError,
    HandlerNotFoundError,
    InfrastructureError,
    NotFoundError,
    Paginated,
    PermissionDeniedError,
    PyFerOxError,
    Response,
    RouteConflictError,
    Streamed,
    Success,
    UnauthorizedError,
    ValidationError,
    map_exception_to_transport,
    normalize_execution_exception,
    to_payload,
)

# HTTP transport
from pyferox.http import HTTPAdapter

# Schema layer
from pyferox.schema import (
    DTO,
    Schema,
    SchemaModel,
    TypedSchema,
    format_validation_error,
    get_schema_metadata,
    parse_input,
    schema_metadata,
    serialize_output,
)

# Auth contracts and implementations
from pyferox.auth import (
    AccessToken,
    AuthBackend,
    Identity,
    InMemorySessionStore,
    PermissionChecker,
    Principal,
    Session,
    SessionAuthBackend,
    SessionStore,
    requires,
)

# Jobs runtime
from pyferox.jobs import InMemoryJobQueue, Job, JobDispatcher, JobExecutionResult, JobQueue, JobStatus, LocalJobWorker

# Cache abstractions
from pyferox.cache import Cache, InMemoryCache

# DB persistence and migrations
from pyferox.db import (
    DBSessionMiddleware,
    MigrationResult,
    Repository,
    SQLAlchemySettings,
    UnitOfWork,
    migration_current,
    migration_downgrade,
    migration_init,
    migration_revision,
    migration_upgrade,
    run_alembic,
    sqlalchemy_module,
)

# Testing helpers
from pyferox.testing import FakeDispatcher, TestHTTPClient, create_test_app, create_test_module, override_dependencies

__all__ = [
    # Namespaces
    "auth",
    "cache",
    "config",
    "core",
    "db",
    "http",
    "jobs",
    "schema",
    "testing",
    # Core runtime
    "App",
    "AppState",
    "ExecutionContext",
    "LifecycleManager",
    "Module",
    "ModuleDefinition",
    "ProviderRegistry",
    "TransportRegistry",
    "module_diagnostics",
    # Contracts
    "Command",
    "Event",
    "ListQuery",
    "Message",
    "PageParams",
    "Query",
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
    # HTTP and schema
    "HTTPAdapter",
    "DTO",
    "Schema",
    "SchemaModel",
    "TypedSchema",
    "format_validation_error",
    "get_schema_metadata",
    "parse_input",
    "schema_metadata",
    "serialize_output",
    # Auth
    "AccessToken",
    "AuthBackend",
    "Identity",
    "InMemorySessionStore",
    "PermissionChecker",
    "Principal",
    "Session",
    "SessionAuthBackend",
    "SessionStore",
    "requires",
    # Jobs and cache
    "InMemoryJobQueue",
    "Job",
    "JobDispatcher",
    "JobExecutionResult",
    "JobQueue",
    "JobStatus",
    "LocalJobWorker",
    "Cache",
    "InMemoryCache",
    # DB
    "DBSessionMiddleware",
    "MigrationResult",
    "Repository",
    "SQLAlchemySettings",
    "UnitOfWork",
    "migration_current",
    "migration_downgrade",
    "migration_init",
    "migration_revision",
    "migration_upgrade",
    "run_alembic",
    "sqlalchemy_module",
    # Testing
    "FakeDispatcher",
    "TestHTTPClient",
    "create_test_app",
    "create_test_module",
    "override_dependencies",
]

