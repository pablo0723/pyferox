"""Minimal ASGI HTTP adapter that dispatches commands and queries."""

from __future__ import annotations

import json
import re
from dataclasses import MISSING, fields, is_dataclass
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin, get_type_hints
from urllib.parse import parse_qs

from pyferox.auth import AuthBackend, PermissionChecker
from pyferox.core import App, ExecutionContext
from pyferox.core.errors import (
    AuthError,
    ForbiddenError,
    RouteConflictError,
    ValidationError,
    map_exception_to_transport,
)
from pyferox.core.results import Paginated, Response, Streamed
from pyferox.schema import get_schema_metadata, parse_input, serialize_output
from pyferox.core.pagination import PageParams, build_page_params, parse_sort


@dataclass(slots=True)
class Route:
    method: str
    path: str
    message_type: type[Any]
    status_code: int
    kind: str = "query"
    permission: str | None = None
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    list_mode: bool = False
    max_page_size: int = 100
    pattern: re.Pattern[str] = field(init=False)

    def __post_init__(self) -> None:
        self.pattern = _compile_route_pattern(self.path)

    def match(self, method: str, path: str) -> dict[str, str] | None:
        if self.method != method.upper():
            return None
        match = self.pattern.match(path)
        if match is None:
            return None
        return match.groupdict()


class HTTPAdapter:
    """ASGI app that maps HTTP requests to app commands and queries."""

    def __init__(
        self,
        app: App,
        *,
        auth_backend: AuthBackend | None = None,
        permission_checker: PermissionChecker | None = None,
    ) -> None:
        self.app = app
        self._auth_backend = auth_backend
        self._permission_checker = permission_checker
        self._routes: list[Route] = []
        self._openapi_path: str | None = None
        self._openapi_title = "PyFerOx API"
        self._openapi_version = "0.1.0"

    def route(
        self,
        method: str,
        path: str,
        message_type: type[Any],
        *,
        kind: str = "query",
        status_code: int = 200,
        permission: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        resolved_permission = permission
        if resolved_permission is None:
            handler = self.app.registry.get_handler(message_type)
            if handler is not None:
                resolved_permission = getattr(handler, "__pyferox_permission__", None)
        self._register(
            Route(
                method=method.upper(),
                path=path,
                message_type=message_type,
                status_code=status_code,
                kind=kind,
                permission=resolved_permission,
                summary=summary,
                description=description,
                tags=tuple(tags or ()),
            )
        )

    def command(
        self,
        method: str,
        path: str,
        message_type: type[Any],
        status_code: int = 202,
        *,
        permission: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.route(
            method,
            path,
            message_type,
            kind="command",
            status_code=status_code,
            permission=permission,
            summary=summary,
            description=description,
            tags=tags,
        )

    def query(
        self,
        method: str,
        path: str,
        message_type: type[Any],
        status_code: int = 200,
        *,
        permission: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.route(
            method,
            path,
            message_type,
            kind="query",
            status_code=status_code,
            permission=permission,
            summary=summary,
            description=description,
            tags=tags,
        )

    def list_query(
        self,
        method: str,
        path: str,
        message_type: type[Any],
        status_code: int = 200,
        *,
        permission: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
        max_page_size: int = 100,
    ) -> None:
        resolved_permission = permission
        if resolved_permission is None:
            handler = self.app.registry.get_handler(message_type)
            if handler is not None:
                resolved_permission = getattr(handler, "__pyferox_permission__", None)
        self._register(
            Route(
                method=method.upper(),
                path=path,
                message_type=message_type,
                status_code=status_code,
                kind="query",
                permission=resolved_permission,
                summary=summary,
                description=description,
                tags=tuple(tags or ()),
                list_mode=True,
                max_page_size=max_page_size,
            )
        )

    def enable_openapi(
        self,
        *,
        path: str = "/openapi.json",
        title: str = "PyFerOx API",
        version: str = "0.1.0",
    ) -> None:
        self._openapi_path = path
        self._openapi_title = title
        self._openapi_version = version

    def openapi_spec(self) -> dict[str, Any]:
        paths: dict[str, dict[str, Any]] = {}
        for route in self._routes:
            path_item = paths.setdefault(route.path, {})
            operation: dict[str, Any] = {
                "operationId": _operation_id(route.method, route.path),
                "responses": {
                    str(route.status_code): {
                        "description": "Successful response",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
            if route.summary:
                operation["summary"] = route.summary
            if route.description:
                operation["description"] = route.description
            if route.tags:
                operation["tags"] = list(route.tags)
            if route.permission is not None:
                operation["security"] = [{"bearerAuth": []}]
                operation.setdefault("x-permission", route.permission)

            schema = _schema_for_type(route.message_type)
            schema_metadata = get_schema_metadata(route.message_type)
            if "title" in schema_metadata:
                schema.setdefault("title", schema_metadata["title"])
            if "description" in schema_metadata:
                schema.setdefault("description", schema_metadata["description"])
            path_params = _path_parameter_names(route.path)
            query_properties = {
                key: value
                for key, value in schema.get("properties", {}).items()
                if key not in path_params
            }
            required = [name for name in schema.get("required", []) if name not in path_params]
            parameters = [
                {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
                for name in path_params
            ]
            if route.kind == "query":
                if route.list_mode:
                    parameters.extend(
                        [
                            {"name": "page", "in": "query", "required": False, "schema": {"type": "integer"}},
                            {"name": "page_size", "in": "query", "required": False, "schema": {"type": "integer"}},
                            {
                                "name": "sort",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "string"},
                                "description": "Comma-separated fields. Prefix with '-' for DESC.",
                            },
                        ]
                    )
                    operation["x-filter-prefix"] = "filter."
                for name, value in query_properties.items():
                    if route.list_mode and name in {"page", "page_size", "sort", "sorts", "filters"}:
                        continue
                    parameters.append(
                        {
                            "name": name,
                            "in": "query",
                            "required": name in required,
                            "schema": value,
                        }
                    )
            if parameters:
                operation["parameters"] = parameters

            if route.kind == "command":
                operation["requestBody"] = {
                    "required": bool(required),
                    "content": {"application/json": {"schema": schema}},
                }
            path_item[route.method.lower()] = operation

        return {
            "openapi": "3.0.3",
            "info": {"title": self._openapi_title, "version": self._openapi_version},
            "paths": paths,
            "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        }

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await _send_json(send, 500, {"error": "Only HTTP scope is supported"})
            return

        method = scope["method"].upper()
        path = scope.get("path", "/")
        if self._openapi_path is not None and method == "GET" and path == self._openapi_path:
            await _send_json(send, 200, self.openapi_spec())
            return
        route, path_params, method_allowed = self._resolve_route(method, path)
        if route is None:
            status = 405 if method_allowed else 404
            message = "Method not allowed" if method_allowed else "Route not found"
            await _send_json(send, status, {"error": message})
            return

        context: ExecutionContext | None = None
        try:
            query_params = _parse_query_params(scope.get("query_string", b""))
            if route.list_mode:
                query_params = _apply_list_query_conventions(
                    route=route,
                    message_type=route.message_type,
                    query_params=query_params,
                )
            body = await _read_json_body(receive)
            payload = {**query_params, **body, **path_params}
            message = parse_input(route.message_type, payload)
            context = ExecutionContext(
                request_id=_header(scope, b"x-request-id") or ExecutionContext().request_id,
                trace_id=_header(scope, b"x-trace-id"),
                transport="http",
            )
            if self._auth_backend is not None:
                token = _bearer_token(_header(scope, b"authorization"))
                if token is None:
                    token = _header(scope, b"x-session-token") or _session_token_from_cookie(_header(scope, b"cookie"))
                context.current_user = await self._auth_backend.authenticate(token)
            if route.permission is not None:
                if context.current_user is None:
                    raise AuthError("Authentication required")
                if self._permission_checker is None:
                    raise ForbiddenError("Permission checker is not configured")
                allowed = await self._permission_checker.allowed(context.current_user, route.permission)
                if not allowed:
                    raise ForbiddenError("Permission denied")
            result = await self.app.execute_with_context(message, context=context)
            if route.list_mode:
                result = _normalize_list_result(result, message)
            if isinstance(result, Streamed):
                await _send_stream(send, route.status_code, result)
                return
            if isinstance(result, Response):
                response_data = _normalize_list_result(result.data, message) if route.list_mode else result.data
                extra_headers = dict(result.headers or {})
                if isinstance(response_data, Paginated):
                    extra_headers.update(_pagination_headers(response_data))
                response_body = serialize_output(response_data if response_data is not None else {})
                await _send_json(send, result.status_code, response_body, extra_headers=extra_headers)
                return
            response_body = serialize_output(result if result is not None else {})
            headers = _pagination_headers(result) if isinstance(result, Paginated) else None
            await _send_json(send, route.status_code, response_body, extra_headers=headers)
        except Exception as exc:
            status, payload = _map_error(exc)
            if context is not None:
                payload.setdefault("request_id", context.request_id)
            await _send_json(send, status, payload)
            return

    def _register(self, route: Route) -> None:
        for existing in self._routes:
            if existing.method == route.method and existing.path == route.path:
                raise RouteConflictError(f"Route already registered: {route.method} {route.path}")
        self._routes.append(route)

    def _resolve_route(self, method: str, path: str) -> tuple[Route | None, dict[str, str], bool]:
        method_allowed = False
        for route in self._routes:
            path_match = route.pattern.match(path)
            if path_match is None:
                continue
            if route.method == method:
                return route, path_match.groupdict(), True
            method_allowed = True
        return None, {}, method_allowed


def _compile_route_pattern(path: str) -> re.Pattern[str]:
    if not path.startswith("/"):
        raise ValueError(f"Route path must start with '/': {path}")
    escaped = re.escape(path).replace(r"\{", "{").replace(r"\}", "}")
    pattern = re.sub(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", r"(?P<\1>[^/]+)", escaped)
    return re.compile(f"^{pattern}$")


def _parse_query_params(raw: bytes) -> dict[str, str]:
    if not raw:
        return {}
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


async def _read_json_body(receive: Any) -> dict[str, Any]:
    body_chunks: list[bytes] = []
    more_body = True
    while more_body:
        event = await receive()
        if event["type"] != "http.request":
            continue
        chunk = event.get("body", b"")
        if chunk:
            body_chunks.append(chunk)
        more_body = event.get("more_body", False)

    if not body_chunks:
        return {}
    raw = b"".join(body_chunks).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid JSON body") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("JSON body must be an object")
    return parsed


def _map_error(exc: Exception) -> tuple[int, dict[str, Any]]:
    return map_exception_to_transport(exc)


def _header(scope: dict[str, Any], key: bytes) -> str | None:
    for header_key, value in scope.get("headers", []):
        if header_key.lower() == key:
            return value.decode("utf-8")
    return None


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _session_token_from_cookie(cookie_header: str | None) -> str | None:
    if cookie_header is None:
        return None
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name in {"session", "session_id"} and value:
            return value
    return None


async def _send_json(
    send: Any,
    status_code: int,
    payload: Any,
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    headers = [(b"content-type", b"application/json")]
    if extra_headers:
        headers.extend((name.lower().encode("utf-8"), value.encode("utf-8")) for name, value in extra_headers.items())
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _send_stream(send: Any, status_code: int, result: Streamed) -> None:
    headers = [(b"content-type", result.content_type.encode("utf-8"))]
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    chunks = result.chunks
    if hasattr(chunks, "__aiter__"):
        async for chunk in chunks:  # type: ignore[union-attr]
            await send({"type": "http.response.body", "body": _stream_chunk_to_bytes(chunk), "more_body": True})
    else:
        for chunk in chunks:
            await send({"type": "http.response.body", "body": _stream_chunk_to_bytes(chunk), "more_body": True})
    await send({"type": "http.response.body", "body": b"", "more_body": False})


def _stream_chunk_to_bytes(chunk: Any) -> bytes:
    if isinstance(chunk, bytes):
        return chunk
    if isinstance(chunk, str):
        return chunk.encode("utf-8")
    if isinstance(chunk, (dict, list)):
        return json.dumps(chunk, default=str).encode("utf-8")
    return str(chunk).encode("utf-8")


def _operation_id(method: str, path: str) -> str:
    cleaned = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    cleaned = cleaned or "root"
    return f"{method.lower()}_{cleaned}"


def _path_parameter_names(path: str) -> list[str]:
    return re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", path)


def _schema_for_type(schema_type: type[Any]) -> dict[str, Any]:
    if is_dataclass(schema_type):
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field_info in fields(schema_type):
            properties[field_info.name] = _schema_for_annotation(field_info.type)
            if field_info.default is MISSING and field_info.default_factory is MISSING:
                required.append(field_info.name)
        return {"type": "object", "properties": properties, "required": required}

    hints = get_type_hints(schema_type, include_extras=True) if hasattr(schema_type, "__mro__") else {}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, annotation in hints.items():
        if name.startswith("_"):
            continue
        properties[name] = _schema_for_annotation(annotation)
        if not hasattr(schema_type, name):
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _schema_for_annotation(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (list, tuple, set):
        inner = args[0] if args else Any
        return {"type": "array", "items": _schema_for_annotation(inner)}
    if origin is dict:
        return {"type": "object"}
    if origin is Any:
        return {}
    if origin is not None and type(None) in args:
        non_none = [arg for arg in args if arg is not type(None)]  # noqa: E721
        schema = _schema_for_annotation(non_none[0]) if non_none else {}
        schema["nullable"] = True
        return schema
    mapping = {str: "string", int: "integer", float: "number", bool: "boolean"}
    if annotation in mapping:
        return {"type": mapping[annotation]}
    return {"type": "object"}


def _apply_list_query_conventions(
    *,
    route: Route,
    message_type: type[Any],
    query_params: dict[str, str],
) -> dict[str, Any]:
    normalized: dict[str, Any] = dict(query_params)
    hints = get_type_hints(message_type, include_extras=True)

    if "page" in hints and _is_page_params_type(hints["page"]):
        page_raw = normalized.pop("page", None)
        page_size_raw = normalized.pop("page_size", None)
        page_value = _coerce_int_or_none(page_raw, key="page")
        page_size_value = _coerce_int_or_none(page_size_raw, key="page_size")
        page = build_page_params(page=page_value, page_size=page_size_value).normalized(max_page_size=route.max_page_size)
        normalized["page"] = {"page": page.page, "page_size": page.page_size}

    if "sorts" in hints and "sort" in normalized:
        normalized["sorts"] = [
            {"field": item.field, "direction": item.direction.value}
            for item in parse_sort(str(normalized.pop("sort")))
        ]

    if "filters" in hints:
        filters = {key.removeprefix("filter."): value for key, value in list(normalized.items()) if key.startswith("filter.")}
        for key in list(normalized.keys()):
            if key.startswith("filter."):
                normalized.pop(key)
        if filters:
            normalized["filters"] = filters

    return normalized


def _is_page_params_type(annotation: Any) -> bool:
    return annotation is PageParams


def _coerce_int_or_none(raw: Any, *, key: str) -> int | None:
    if raw is None:
        return None
    try:
        return int(str(raw))
    except ValueError as exc:
        raise ValidationError(f"Invalid integer for {key}") from exc


def _normalize_list_result(result: Any, message: Any) -> Any:
    if isinstance(result, Paginated):
        return result
    if isinstance(result, list):
        page = _message_page(message)
        return Paginated(items=result, total=len(result), page=page.page, page_size=page.page_size)
    return result


def _message_page(message: Any) -> PageParams:
    page = getattr(message, "page", None)
    if isinstance(page, PageParams):
        return page
    return PageParams()


def _pagination_headers(paginated: Paginated) -> dict[str, str]:
    return {
        "x-total-count": str(paginated.total),
        "x-page": str(paginated.page),
        "x-page-size": str(paginated.page_size),
    }
