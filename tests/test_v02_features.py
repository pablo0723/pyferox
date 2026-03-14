import asyncio
import json
import unittest

from pyferox import API, APIView, BasePermission, PageNumberPagination, Serializer


class ItemQuerySerializer(Serializer):
    page: int
    page_size: int


class DenyAllPermission(BasePermission):
    def has_permission(self, request, view) -> bool:
        return False


class ItemsPagination(PageNumberPagination):
    page_size = 2
    max_page_size = 50


class ItemsView(APIView):
    query_serializer_class = ItemQuerySerializer
    pagination_class = ItemsPagination

    def get(self, request):
        return [{"id": i} for i in range(1, 8)]


class OnlyGetView(APIView):
    def get(self, request):
        return {"ok": True}


class V02FeaturesTests(unittest.TestCase):
    def setUp(self):
        self.app = API()

        @self.app.get("/query", query_schema=ItemQuerySerializer)
        def query_view(request):
            return {"page": request.query_data["page"], "page_size": request.query_data["page_size"]}

        @self.app.get("/private", permission_classes=[DenyAllPermission])
        def private_view(request):
            return {"ok": True}

        self.app.add_api_view("/items", ItemsView)
        self.app.add_api_view("/only-get", OnlyGetView)

    def test_query_parsing(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/query?page=2&page_size=5"))
        self.assertEqual(status, 200)
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["page_size"], 5)

    def test_query_parsing_error(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/query?page=bad&page_size=5"))
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], 422)

    def test_permissions(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/private"))
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], 403)

    def test_class_based_view_pagination(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/items?page=2&page_size=3"))
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 7)
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["page_size"], 3)
        self.assertEqual(len(body["results"]), 3)
        self.assertEqual(body["results"][0]["id"], 4)

    def test_method_not_allowed(self):
        status, body = asyncio.run(call_app(self.app, "POST", "/only-get", payload={"x": 1}))
        self.assertEqual(status, 405)
        self.assertEqual(body["error"]["code"], 405)


async def call_app(app, method, path, payload=None):
    sent = []
    body = b""
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    raw_path, _, query = path.partition("?")
    scope = {
        "type": "http",
        "method": method,
        "path": raw_path,
        "headers": [(b"content-type", b"application/json")],
        "query_string": query.encode("utf-8"),
    }
    await app(scope, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    body_bytes = next(item["body"] for item in sent if item["type"] == "http.response.body")
    return status, json.loads(body_bytes.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
