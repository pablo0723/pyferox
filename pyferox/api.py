from __future__ import annotations

import inspect

from .authentication import BaseAuthentication
from .errors import HTTPError, error_payload
from .openapi import build_openapi_schema
from .permissions import AllowAny
from .request import Request
from .response import JSONResponse, ensure_response
from .routing import Router
from .serializers import Serializer
from .views import APIView


class API:
    def __init__(self):
        self.router = Router()

    def route(
        self,
        method: str,
        path: str,
        *,
        input_schema=None,
        output_schema=None,
        query_schema=None,
        permission_classes=None,
        authentication_classes=None,
        filter_backends=None,
        tags=None,
    ):
        method = method.upper()
        permission_classes = permission_classes or [AllowAny]
        authentication_classes = authentication_classes or []
        filter_backends = filter_backends or []
        tags = tags or []

        def decorator(handler):
            self.router.add(
                method,
                path,
                handler,
                input_schema=input_schema,
                output_schema=output_schema,
                query_schema=query_schema,
                permission_classes=permission_classes,
                authentication_classes=authentication_classes,
                filter_backends=filter_backends,
                tags=tags,
            )
            return handler

        return decorator

    def get(
        self,
        path: str,
        *,
        input_schema=None,
        output_schema=None,
        query_schema=None,
        permission_classes=None,
        authentication_classes=None,
        filter_backends=None,
        tags=None,
    ):
        return self.route(
            "GET",
            path,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            permission_classes=permission_classes,
            authentication_classes=authentication_classes,
            filter_backends=filter_backends,
            tags=tags,
        )

    def post(
        self,
        path: str,
        *,
        input_schema=None,
        output_schema=None,
        query_schema=None,
        permission_classes=None,
        authentication_classes=None,
        filter_backends=None,
        tags=None,
    ):
        return self.route(
            "POST",
            path,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            permission_classes=permission_classes,
            authentication_classes=authentication_classes,
            filter_backends=filter_backends,
            tags=tags,
        )

    def put(
        self,
        path: str,
        *,
        input_schema=None,
        output_schema=None,
        query_schema=None,
        permission_classes=None,
        authentication_classes=None,
        filter_backends=None,
        tags=None,
    ):
        return self.route(
            "PUT",
            path,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            permission_classes=permission_classes,
            authentication_classes=authentication_classes,
            filter_backends=filter_backends,
            tags=tags,
        )

    def patch(
        self,
        path: str,
        *,
        input_schema=None,
        output_schema=None,
        query_schema=None,
        permission_classes=None,
        authentication_classes=None,
        filter_backends=None,
        tags=None,
    ):
        return self.route(
            "PATCH",
            path,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            permission_classes=permission_classes,
            authentication_classes=authentication_classes,
            filter_backends=filter_backends,
            tags=tags,
        )

    def delete(
        self,
        path: str,
        *,
        input_schema=None,
        output_schema=None,
        query_schema=None,
        permission_classes=None,
        authentication_classes=None,
        filter_backends=None,
        tags=None,
    ):
        return self.route(
            "DELETE",
            path,
            input_schema=input_schema,
            output_schema=output_schema,
            query_schema=query_schema,
            permission_classes=permission_classes,
            authentication_classes=authentication_classes,
            filter_backends=filter_backends,
            tags=tags,
        )

    def add_api_view(self, path: str, view_class: type[APIView]):
        if not issubclass(view_class, APIView):
            raise TypeError("view_class must be APIView subclass")
        view_callable = view_class.as_view()
        for method in view_class.allowed_methods():
            self.router.add(
                method,
                path,
                view_callable,
                permission_classes=view_class.permission_classes,
                authentication_classes=view_class.authentication_classes,
                filter_backends=view_class.filter_backends,
                query_schema=view_class.query_serializer_class,
                tags=[view_class.__name__],
            )

    def include_router(self, router):
        router.bind(self)

    def openapi(self, *, title: str = "PyFerOx API", version: str = "0.1.0"):
        return build_openapi_schema(self.router.routes, title=title, version=version)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        route, path_params, path_matched = self.router.resolve(scope["method"].upper(), scope["path"])
        if route is None:
            if path_matched:
                await self._send_response(
                    send,
                    JSONResponse(error_payload(405, "method not allowed"), status_code=405),
                )
                return
            await self._send_response(
                send,
                JSONResponse(error_payload(404, "route not found"), status_code=404),
            )
            return
        try:
            request = await Request.from_asgi(scope, receive, path_params)
            await self._authenticate(route.authentication_classes or [], request)
            await self._check_permissions(route.permission_classes or [AllowAny], request)
            if route.query_schema is not None:
                request._query_cache = await self._apply_query_contract(route.query_schema, request.query_params)
            if route.input_schema is not None:
                request._json_cache = await self._apply_input_contract(route.input_schema, request.json_body)
            result = route.handler(request)
            if inspect.isawaitable(result):
                result = await result
            if route.filter_backends and isinstance(result, list):
                result = await self._apply_filter_backends(route.filter_backends, request, result)
            if route.output_schema is not None:
                result = await self._apply_output_contract(route.output_schema, result)
            response = ensure_response(result)
        except HTTPError as exc:
            response = JSONResponse(error_payload(exc.status_code, exc.message, exc.details), status_code=exc.status_code)
        except Exception:
            response = JSONResponse(error_payload(500, "internal server error"), status_code=500)
        await self._send_response(send, response)

    async def _send_response(self, send, response):
        status_code, headers, body = response.as_asgi()
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    async def _apply_query_contract(contract, payload: dict[str, str]):
        if isinstance(contract, type) and issubclass(contract, Serializer):
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

    @staticmethod
    async def _check_permissions(permission_classes, request):
        for permission_class in permission_classes:
            permission = permission_class()
            allowed = permission.has_permission(request, None)
            if inspect.isawaitable(allowed):
                allowed = await allowed
            if not allowed:
                raise HTTPError(403, "permission denied")

    @staticmethod
    async def _authenticate(authentication_classes, request):
        request.user = None
        request.auth = None
        for auth_class in authentication_classes:
            if not issubclass(auth_class, BaseAuthentication):
                raise TypeError("authentication_classes items must inherit BaseAuthentication")
            auth = auth_class()
            auth_result = auth.authenticate(request)
            if inspect.isawaitable(auth_result):
                auth_result = await auth_result
            if auth_result is None:
                continue
            request.user, request.auth = auth_result
            return

    @staticmethod
    async def _apply_filter_backends(filter_backends, request, queryset):
        out = queryset
        for backend_class in filter_backends:
            backend = backend_class()
            out = backend.filter_queryset(request, out, None)
            if inspect.isawaitable(out):
                out = await out
        return out
