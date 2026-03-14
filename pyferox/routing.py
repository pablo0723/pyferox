from __future__ import annotations

from dataclasses import dataclass

from .rust_bridge import parse_path_params


@dataclass
class Route:
    method: str
    path_pattern: str
    handler: callable
    input_schema: type | None = None
    output_schema: type | None = None
    query_schema: type | None = None
    permission_classes: list[type] | None = None
    authentication_classes: list[type] | None = None
    filter_backends: list[type] | None = None
    tags: list[str] | None = None

    def match(self, method: str, path: str):
        if self.method != method:
            return None
        return parse_path_params(self.path_pattern, path)

    def match_path(self, path: str):
        return parse_path_params(self.path_pattern, path)


class Router:
    def __init__(self):
        self.routes: list[Route] = []

    def add(
        self,
        method: str,
        path_pattern: str,
        handler,
        input_schema=None,
        output_schema=None,
        query_schema=None,
        permission_classes=None,
        authentication_classes=None,
        filter_backends=None,
        tags=None,
    ):
        self.routes.append(
            Route(
                method,
                path_pattern,
                handler,
                input_schema=input_schema,
                output_schema=output_schema,
                query_schema=query_schema,
                permission_classes=permission_classes,
                authentication_classes=authentication_classes,
                filter_backends=filter_backends,
                tags=tags,
            )
        )

    def resolve(self, method: str, path: str):
        path_matched = False
        for route in self.routes:
            path_params = route.match(method, path)
            if path_params is not None:
                return route, path_params, False
            maybe_path = route.match_path(path)
            if maybe_path is not None:
                path_matched = True
        return None, None, path_matched
