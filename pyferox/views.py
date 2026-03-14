from __future__ import annotations

import inspect

from .authentication import BaseAuthentication
from .errors import HTTPError
from .permissions import AllowAny
from .serializers import Serializer


class APIView:
    permission_classes = [AllowAny]
    authentication_classes = []
    filter_backends = []
    filterset_fields = []
    search_fields = []
    ordering_fields = []
    query_serializer_class = None
    pagination_class = None
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def __init__(self):
        self.request = None
        self.paginator = None

    @classmethod
    def allowed_methods(cls):
        methods = []
        for name in cls.http_method_names:
            if hasattr(cls, name):
                methods.append(name.upper())
        return methods

    @classmethod
    def as_view(cls):
        async def view(request):
            self = cls()
            return await self.dispatch(request)

        view.view_class = cls
        return view

    async def dispatch(self, request):
        self.request = request
        await self.perform_authentication(request)
        await self.check_permissions(request)
        await self.parse_query(request)

        method_name = request.method.lower()
        handler = getattr(self, method_name, None)
        if handler is None:
            raise HTTPError(405, "method not allowed")
        result = handler(request)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, list):
            result = await self.filter_queryset(result)
            page = await self.paginate_queryset(result)
            if page is not None:
                return await self.get_paginated_response(page)
        return result

    async def perform_authentication(self, request):
        request.user = None
        request.auth = None
        for authenticator in self.get_authenticators():
            auth_result = authenticator.authenticate(request)
            if inspect.isawaitable(auth_result):
                auth_result = await auth_result
            if auth_result is None:
                continue
            request.user, request.auth = auth_result
            return

    def get_authenticators(self):
        out = []
        for auth_class in self.authentication_classes:
            if not issubclass(auth_class, BaseAuthentication):
                raise TypeError("authentication_classes items must inherit BaseAuthentication")
            out.append(auth_class())
        return out

    def get_permissions(self):
        return [permission() for permission in self.permission_classes]

    async def check_permissions(self, request):
        for permission in self.get_permissions():
            allowed = permission.has_permission(request, self)
            if inspect.isawaitable(allowed):
                allowed = await allowed
            if not allowed:
                raise HTTPError(403, "permission denied")

    async def check_object_permissions(self, request, obj):
        for permission in self.get_permissions():
            allowed = permission.has_object_permission(request, self, obj)
            if inspect.isawaitable(allowed):
                allowed = await allowed
            if not allowed:
                raise HTTPError(403, "permission denied")

    async def parse_query(self, request):
        serializer_cls = self.query_serializer_class
        if serializer_cls is None:
            return request.query_params
        if not (isinstance(serializer_cls, type) and issubclass(serializer_cls, Serializer)):
            raise TypeError("query_serializer_class must be a Serializer subclass")
        parsed = serializer_cls.parse_query_params(request.query_params)
        if inspect.isawaitable(parsed):
            parsed = await parsed
        request._query_cache = parsed
        return parsed

    async def filter_queryset(self, queryset):
        out = queryset
        for backend_class in self.filter_backends:
            backend = backend_class()
            out = backend.filter_queryset(self.request, out, self)
            if inspect.isawaitable(out):
                out = await out
        return out

    async def paginate_queryset(self, queryset):
        if self.pagination_class is None:
            return None
        self.paginator = self.pagination_class()
        page = self.paginator.paginate_queryset(queryset, self.request, view=self)
        if inspect.isawaitable(page):
            page = await page
        return page

    async def get_paginated_response(self, data):
        if self.paginator is None:
            return data
        response = self.paginator.get_paginated_response(data)
        if inspect.isawaitable(response):
            response = await response
        return response
