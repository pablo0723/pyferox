"""RPC transport runtime for inter-service communication."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

from pyferox.core import App, ExecutionContext
from pyferox.core.errors import FrameworkError, InfrastructureError, map_exception_to_transport
from pyferox.reliability import IdempotencyStore, RetryClassifier, RetryPolicy, default_retry_classifier
from pyferox.schema import parse_input


@dataclass(slots=True)
class RPCRequest:
    method: str
    payload: Any = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float | None = None
    idempotency_key: str | None = None
    idempotency_ttl_seconds: float | None = None


@dataclass(slots=True)
class RPCResponse:
    ok: bool
    status_code: int
    data: Any = None
    error: dict[str, Any] | None = None


class RPCError(FrameworkError):
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {"type": "rpc_error", "error": "RPC request failed"}
        super().__init__(payload.get("error", "RPC request failed"))
        self.status_code = status_code
        self.payload = payload


class RPCTransport(Protocol):
    async def send(self, service: str, request: RPCRequest) -> RPCResponse:
        ...


class RPCServer:
    """Service-side RPC request mapper backed by App dispatch."""

    def __init__(self, app: App, *, idempotency_store: IdempotencyStore | None = None) -> None:
        self.app = app
        self._methods: dict[str, type[Any]] = {}
        self._idempotency_store = idempotency_store

    def register(self, method: str, message_type: type[Any]) -> None:
        if method in self._methods:
            raise ValueError(f"RPC method already registered: {method}")
        self._methods[method] = message_type

    async def handle(self, request: RPCRequest) -> RPCResponse:
        message_type = self._methods.get(request.method)
        if message_type is None:
            return RPCResponse(
                ok=False,
                status_code=404,
                error={"type": "rpc_method_not_found", "error": f"Method not found: {request.method}"},
            )

        if self._idempotency_store is not None and request.idempotency_key is not None:
            cached = await self._idempotency_store.result(request.idempotency_key)
            if cached is not None:
                return RPCResponse(ok=True, status_code=200, data=cached)
            reserved = await self._idempotency_store.reserve(
                request.idempotency_key,
                ttl_seconds=request.idempotency_ttl_seconds,
            )
            if not reserved:
                return RPCResponse(
                    ok=False,
                    status_code=409,
                    error={"type": "idempotency_conflict", "error": "Idempotency key is already in progress"},
                )

        context: ExecutionContext | None = None
        try:
            context = ExecutionContext(
                request_id=str(request.metadata.get("request_id", ExecutionContext().request_id)),
                trace_id=_to_optional_str(request.metadata.get("trace_id")),
                transport="rpc",
            )
            message = parse_input(message_type, request.payload)
            result = await self.app.execute_with_context(message, context=context)
            if self._idempotency_store is not None and request.idempotency_key is not None:
                await self._idempotency_store.complete(request.idempotency_key, result=result)
            return RPCResponse(ok=True, status_code=200, data=result)
        except Exception as exc:
            if self._idempotency_store is not None and request.idempotency_key is not None:
                await self._idempotency_store.fail(request.idempotency_key, error=str(exc))
            status, payload = map_exception_to_transport(exc)
            if context is not None:
                payload.setdefault("request_id", context.request_id)
            return RPCResponse(ok=False, status_code=status, error=payload)


class InMemoryRPCTransport:
    """In-memory RPC transport used for single-process and test topologies."""

    def __init__(self, *, default_timeout_seconds: float | None = 5.0) -> None:
        self._servers: dict[str, RPCServer] = {}
        self._default_timeout_seconds = default_timeout_seconds

    def register_service(self, service: str, server: RPCServer) -> None:
        if service in self._servers:
            raise ValueError(f"RPC service already registered: {service}")
        self._servers[service] = server

    async def send(self, service: str, request: RPCRequest) -> RPCResponse:
        server = self._servers.get(service)
        if server is None:
            return RPCResponse(
                ok=False,
                status_code=404,
                error={"type": "rpc_service_not_found", "error": f"Service not found: {service}"},
            )

        timeout_seconds = request.timeout_seconds
        if timeout_seconds is None:
            timeout_seconds = self._default_timeout_seconds
        if timeout_seconds is None:
            return await server.handle(request)
        try:
            return await asyncio.wait_for(server.handle(request), timeout=timeout_seconds)
        except TimeoutError:
            return RPCResponse(
                ok=False,
                status_code=504,
                error={"type": "rpc_timeout", "error": "RPC request timed out"},
            )


class RPCClient:
    def __init__(
        self,
        *,
        transport: RPCTransport,
        service: str,
        retry_policy: RetryPolicy | None = None,
        retry_classifier: RetryClassifier | None = None,
    ) -> None:
        self.transport = transport
        self.service = service
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=1)
        self.retry_classifier = retry_classifier or default_retry_classifier

    async def request(
        self,
        method: str,
        payload: Any,
        *,
        timeout_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        idempotency_ttl_seconds: float | None = None,
    ) -> RPCResponse:
        attempt = 1
        while True:
            request = RPCRequest(
                method=method,
                payload=payload,
                metadata=metadata or {},
                timeout_seconds=timeout_seconds,
                idempotency_key=idempotency_key,
                idempotency_ttl_seconds=idempotency_ttl_seconds,
            )
            response = await self.transport.send(self.service, request)
            if response.ok:
                return response

            decision = self.retry_classifier(
                InfrastructureError((response.error or {}).get("error", "rpc error"))
            )
            if not self.retry_policy.should_retry(attempt=attempt, decision=decision):
                return response
            await asyncio.sleep(self.retry_policy.next_delay_seconds(attempt=attempt))
            attempt += 1

    async def call(
        self,
        method: str,
        payload: Any,
        *,
        timeout_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        idempotency_ttl_seconds: float | None = None,
    ) -> Any:
        response = await self.request(
            method,
            payload,
            timeout_seconds=timeout_seconds,
            metadata=metadata,
            idempotency_key=idempotency_key,
            idempotency_ttl_seconds=idempotency_ttl_seconds,
        )
        if response.ok:
            return response.data
        raise RPCError(response.status_code, payload=response.error)


def _to_optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
