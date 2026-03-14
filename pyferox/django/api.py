from __future__ import annotations

import inspect

from django.http import HttpResponseNotAllowed
from django.urls import path

from pyferox.errors import HTTPError, error_payload
from pyferox.request import Request
from pyferox.response import JSONResponse, ensure_response
from pyferox.serializers import Serializer


class DjangoAPI:
    def __init__(self, prefix: str = ""):
        self.prefix = prefix.strip("/")
        self._routes = []

    def route(self, method: str, pattern: str, *, input_schema=None, output_schema=None, query_schema=None, name=None):
        http_method = method.upper()

        def decorator(handler):
            django_pattern = _django_pattern(self.prefix, pattern)
            route_name = name or handler.__name__
            django_view = self._build_view(
                http_method,
                handler,
                input_schema=input_schema,
                output_schema=output_schema,
                query_schema=query_schema,
            )
            self._routes.append((django_pattern, django_view, route_name))
            return handler

        return decorator

    def get(self, pattern: str, *, input_schema=None, output_schema=None, query_schema=None, name=None):
        return self.route(
            "GET",
            pattern,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            name=name,
        )

    def post(self, pattern: str, *, input_schema=None, output_schema=None, query_schema=None, name=None):
        return self.route(
            "POST",
            pattern,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            name=name,
        )

    def put(self, pattern: str, *, input_schema=None, output_schema=None, query_schema=None, name=None):
        return self.route(
            "PUT",
            pattern,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            name=name,
        )

    def patch(self, pattern: str, *, input_schema=None, output_schema=None, query_schema=None, name=None):
        return self.route(
            "PATCH",
            pattern,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            name=name,
        )

    def delete(self, pattern: str, *, input_schema=None, output_schema=None, query_schema=None, name=None):
        return self.route(
            "DELETE",
            pattern,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            name=name,
        )

    @property
    def urls(self):
        return [path(pattern, view, name=name) for pattern, view, name in self._routes]

    def _build_view(self, method: str, handler, *, input_schema=None, output_schema=None, query_schema=None):
        async def django_view(request, **kwargs):
            if request.method.upper() != method:
                return HttpResponseNotAllowed([method])
            try:
                wrapped = Request.from_django(request, kwargs)
                if query_schema is not None:
                    wrapped._query_cache = await _apply_query_contract(query_schema, wrapped.query_params)
                if input_schema is not None:
                    wrapped._json_cache = await _apply_input_contract(input_schema, wrapped.json_body)
                result = handler(wrapped)
                if inspect.isawaitable(result):
                    result = await result
                if output_schema is not None:
                    result = await _apply_output_contract(output_schema, result)
                response = ensure_response(result)
            except HTTPError as exc:
                response = JSONResponse(error_payload(exc.status_code, exc.message, exc.details), status_code=exc.status_code)
            except Exception:
                response = JSONResponse(error_payload(500, "internal server error"), status_code=500)
            status, headers, body = response.as_asgi()
            return _to_django_response(status, headers, body)

        return django_view


async def _apply_input_contract(contract, payload: dict):
    if isinstance(contract, type) and issubclass(contract, Serializer):
        serializer = contract(data=payload)
        valid = serializer.ais_valid(raise_exception=True) if hasattr(serializer, "ais_valid") else serializer.is_valid(
            raise_exception=True
        )
        if inspect.isawaitable(valid):
            await valid
        return serializer.validated_data
    if hasattr(contract, "validate"):
        result = contract.validate(payload)
        if inspect.isawaitable(result):
            result = await result
        return result
    raise TypeError("input_schema must implement validate() or be Serializer subclass")


async def _apply_output_contract(contract, payload):
    if isinstance(contract, type) and issubclass(contract, Serializer):
        many = isinstance(payload, list)
        serializer = contract(instance=payload, many=many)
        return serializer.data
    if hasattr(contract, "validate"):
        result = contract.validate(payload)
        if inspect.isawaitable(result):
            result = await result
        return result
    raise TypeError("output_schema must implement validate() or be Serializer subclass")


async def _apply_query_contract(contract, payload: dict[str, str]):
    if isinstance(contract, type) and issubclass(contract, Serializer):
        if hasattr(contract, "aparse_query_params"):
            return await contract.aparse_query_params(payload)
        result = contract.parse_query_params(payload)
        if inspect.isawaitable(result):
            result = await result
        return result
    if hasattr(contract, "validate_query"):
        result = contract.validate_query(payload)
        if inspect.isawaitable(result):
            result = await result
        return result
    raise TypeError("query_schema must implement validate_query() or be Serializer subclass")


def _to_django_response(status: int, headers, body: bytes):
    header_map = {name.decode("latin-1"): value.decode("latin-1") for name, value in headers}
    from django.http import HttpResponse

    return HttpResponse(body, status=status, headers=header_map)


def _django_pattern(prefix: str, pattern: str):
    normalized = pattern.strip("/")
    if prefix:
        normalized = f"{prefix}/{normalized}" if normalized else prefix
    normalized = _replace_path_params(normalized)
    return normalized


def _replace_path_params(pattern: str):
    out = pattern
    while "{" in out and "}" in out:
        start = out.index("{")
        end = out.index("}", start)
        key = out[start + 1 : end]
        out = out[:start] + f"<str:{key}>" + out[end + 1 :]
    return out
