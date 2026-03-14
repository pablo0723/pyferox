import asyncio
import json
import unittest

from pyferox import (
    API,
    FieldFilterBackend,
    IsAuthenticated,
    OrderingFilter,
    ResourceRouter,
    SearchFilter,
    Serializer,
    TokenAuthentication,
    ViewSet,
)


class ProductSerializer(Serializer):
    id: int
    name: str
    category: str


PRODUCTS = [
    {"id": 1, "name": "Apple", "category": "fruit"},
    {"id": 2, "name": "Banana", "category": "fruit"},
    {"id": 3, "name": "Carrot", "category": "vegetable"},
]


class ProductViewSet(ViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    filter_backends = [FieldFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category"]
    search_fields = ["name"]
    ordering_fields = ["id", "name"]

    def get_queryset(self):
        return list(PRODUCTS)

    def list(self, request):
        return self.get_queryset()

    def retrieve(self, request):
        return self.get_object()

    def create(self, request):
        payload = request.data
        return payload


class V03FeaturesTests(unittest.TestCase):
    def setUp(self):
        self.app = API()
        router = ResourceRouter()
        router.register("products", ProductViewSet, basename="products")
        self.app.include_router(router)

    def test_viewset_auth_required(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/products"))
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], 403)

    def test_viewset_list_filter_search_ordering(self):
        status, body = asyncio.run(
            call_app(
                self.app,
                "GET",
                "/products?category=fruit&search=a&ordering=-name",
                token="abc123",
            )
        )
        self.assertEqual(status, 200)
        self.assertEqual([item["name"] for item in body], ["Banana", "Apple"])

    def test_viewset_retrieve(self):
        status, body = asyncio.run(call_app(self.app, "GET", "/products/3", token="abc123"))
        self.assertEqual(status, 200)
        self.assertEqual(body["name"], "Carrot")

    def test_openapi_generation(self):
        schema = self.app.openapi(title="Demo API", version="0.3.0")
        self.assertEqual(schema["openapi"], "3.1.0")
        self.assertIn("/products", schema["paths"])
        self.assertIn("/products/{id}", schema["paths"])
        self.assertIn("get", schema["paths"]["/products"])
        self.assertIn("post", schema["paths"]["/products"])
        self.assertIn("ProductSerializer", schema["components"]["schemas"])


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
