import asyncio
import json
import unittest

from pyferox import API, APIView, BasePermission, Serializer
from pyferox.authentication import BaseAuthentication
from pyferox.filters import BaseFilterBackend
from pyferox.pagination import BasePagination


class AsyncAuth(BaseAuthentication):
    async def authenticate(self, request):
        header = request.headers.get("authorization", "")
        if header == "Token ok":
            return {"id": "u1"}, "ok"
        return None


class AsyncPermission(BasePermission):
    async def has_permission(self, request, view) -> bool:
        return request.user is not None


class AsyncFilter(BaseFilterBackend):
    async def filter_queryset(self, request, queryset, view):
        return [item for item in queryset if item["id"] % 2 == 0]


class AsyncPagination(BasePagination):
    async def paginate_queryset(self, queryset, request, view=None):
        return list(queryset)[:1]

    async def get_paginated_response(self, data):
        return {"results": data, "count": len(data)}


class QuerySerializer(Serializer):
    q: str


class AsyncItemsView(APIView):
    authentication_classes = [AsyncAuth]
    permission_classes = [AsyncPermission]
    filter_backends = [AsyncFilter]
    pagination_class = AsyncPagination
    query_serializer_class = QuerySerializer

    async def get(self, request):
        return [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]


class AsyncHooksTests(unittest.TestCase):
    def setUp(self):
        self.app = API()

        @self.app.get(
            "/fn-items",
            authentication_classes=[AsyncAuth],
            permission_classes=[AsyncPermission],
            filter_backends=[AsyncFilter],
        )
        async def fn_items(request):
            return [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]

        self.app.add_api_view("/cbv-items", AsyncItemsView)

    def test_async_hooks_on_function_route(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/fn-items", token="ok"))
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in body], [2, 4])

    def test_async_hooks_on_function_route_forbidden(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/fn-items"))
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], 403)

    def test_async_hooks_on_class_based_view(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/cbv-items?q=test", token="ok"))
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], 2)


async def call_app(app, method, path, payload=None, token=None):
    sent = []
    body = b""
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    raw_path, _, query = path.partition("?")
    headers = [(b"content-type", b"application/json")]
    if token is not None:
        headers.append((b"authorization", f"Token {token}".encode("utf-8")))
    scope = {
        "type": "http",
        "method": method,
        "path": raw_path,
        "headers": headers,
        "query_string": query.encode("utf-8"),
    }
    await app(scope, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    body_bytes = next(item["body"] for item in sent if item["type"] == "http.response.body")
    return status, json.loads(body_bytes.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
