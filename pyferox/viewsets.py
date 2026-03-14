from __future__ import annotations

import inspect

from .errors import HTTPError
from .views import APIView


class ViewSet(APIView):
    lookup_field = "id"
    serializer_class = None
    list_query_serializer_class = None
    detail_query_serializer_class = None

    def get_queryset(self):
        return []

    def get_object(self):
        lookup = self.request.path_params.get(self.lookup_field)
        for item in self.get_queryset():
            if str(_value(item, self.lookup_field)) == str(lookup):
                return item
        raise HTTPError(404, "not found")

    def get_serializer_class(self):
        return self.serializer_class

    def get_serializer(self, *args, **kwargs):
        cls = self.get_serializer_class()
        if cls is None:
            raise TypeError("serializer_class is required for this action")
        return cls(*args, **kwargs)

    async def dispatch_action(self, request, action_name: str):
        self.request = request
        await self.perform_authentication(request)
        await self.check_permissions(request)
        await self.parse_query(request)
        handler = getattr(self, action_name, None)
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


class ResourceRouter:
    def __init__(self):
        self.registry = []

    def register(self, prefix: str, viewset_class: type[ViewSet], basename: str | None = None):
        if not issubclass(viewset_class, ViewSet):
            raise TypeError("viewset_class must inherit ViewSet")
        normalized = prefix.strip("/")
        self.registry.append((normalized, viewset_class, basename or normalized))

    def bind(self, api):
        for prefix, viewset_class, basename in self.registry:
            self._bind_viewset(api, prefix, viewset_class, basename)

    def _bind_viewset(self, api, prefix: str, viewset_class: type[ViewSet], basename: str):
        list_path = f"/{prefix}"
        detail_path = f"/{prefix}" + "/{" + viewset_class.lookup_field + "}"
        tags = [basename]

        if hasattr(viewset_class, "list"):
            api.route(
                "GET",
                list_path,
                output_schema=viewset_class.serializer_class,
                query_schema=viewset_class.list_query_serializer_class or viewset_class.query_serializer_class,
                permission_classes=viewset_class.permission_classes,
                authentication_classes=viewset_class.authentication_classes,
                tags=tags,
            )(self._make_handler(viewset_class, "list"))
        if hasattr(viewset_class, "create"):
            api.route(
                "POST",
                list_path,
                input_schema=viewset_class.serializer_class,
                output_schema=viewset_class.serializer_class,
                permission_classes=viewset_class.permission_classes,
                authentication_classes=viewset_class.authentication_classes,
                tags=tags,
            )(self._make_handler(viewset_class, "create"))
        if hasattr(viewset_class, "retrieve"):
            api.route(
                "GET",
                detail_path,
                output_schema=viewset_class.serializer_class,
                query_schema=viewset_class.detail_query_serializer_class or viewset_class.query_serializer_class,
                permission_classes=viewset_class.permission_classes,
                authentication_classes=viewset_class.authentication_classes,
                tags=tags,
            )(self._make_handler(viewset_class, "retrieve"))
        if hasattr(viewset_class, "update"):
            api.route(
                "PUT",
                detail_path,
                input_schema=viewset_class.serializer_class,
                output_schema=viewset_class.serializer_class,
                permission_classes=viewset_class.permission_classes,
                authentication_classes=viewset_class.authentication_classes,
                tags=tags,
            )(self._make_handler(viewset_class, "update"))
        if hasattr(viewset_class, "partial_update"):
            api.route(
                "PATCH",
                detail_path,
                input_schema=viewset_class.serializer_class,
                output_schema=viewset_class.serializer_class,
                permission_classes=viewset_class.permission_classes,
                authentication_classes=viewset_class.authentication_classes,
                tags=tags,
            )(self._make_handler(viewset_class, "partial_update"))
        if hasattr(viewset_class, "destroy"):
            api.route(
                "DELETE",
                detail_path,
                permission_classes=viewset_class.permission_classes,
                authentication_classes=viewset_class.authentication_classes,
                tags=tags,
            )(self._make_handler(viewset_class, "destroy"))

    @staticmethod
    def _make_handler(viewset_class: type[ViewSet], action_name: str):
        async def handler(request):
            view = viewset_class()
            return await view.dispatch_action(request, action_name)

        handler.__name__ = f"{viewset_class.__name__}_{action_name}"
        return handler


def _value(item, field, default=None):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)
