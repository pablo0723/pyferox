import asyncio
import json
import unittest

from pyferox import API, Field, Nested, Schema, Serializer


class InputSerializer(Serializer):
    id: int = Field(read_only=True)
    name: str
    age: int = Field(required=False, default=18)
    nickname: str = Field(required=False, allow_null=True)
    password: str = Field(write_only=True)


class QuerySerializer(Serializer):
    page: int = Field(required=False, default=1)
    page_size: int = Field(required=False, default=20)
    active: bool
    term: str = Field(required=False, allow_null=True)


class QuerySchema(Schema):
    page: int
    active: bool


class ProfileSerializer(Serializer):
    city: str


class AliasNestedSerializer(Serializer):
    display_name: str = Field(alias="displayName", source="name")
    profile: dict = Nested(ProfileSerializer, source="profile_data")


class AsyncQueryContract:
    @staticmethod
    async def validate_query(params):
        return {"q": params.get("q", "").upper()}


class SerializerFieldOptionsTests(unittest.TestCase):
    def test_defaults_and_read_write_flags(self):
        serializer = InputSerializer(data={"name": "Ada", "password": "secret"})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["name"], "Ada")
        self.assertEqual(serializer.validated_data["age"], 18)
        self.assertNotIn("id", serializer.validated_data)

    def test_allow_null(self):
        serializer = InputSerializer(data={"name": "Ada", "password": "secret", "nickname": None})
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data["nickname"])

    def test_partial_update(self):
        serializer = InputSerializer(data={"age": 21}, partial=True)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["age"], 21)
        self.assertNotIn("name", serializer.validated_data)

    def test_unknown_field_is_error(self):
        serializer = InputSerializer(data={"name": "Ada", "password": "secret", "extra": 1})
        self.assertFalse(serializer.is_valid())
        self.assertIn("extra", serializer.errors)

    def test_write_only_not_in_output(self):
        serializer = InputSerializer(instance={"id": 1, "name": "Ada", "age": 30, "password": "secret"})
        self.assertEqual(serializer.data, {"id": 1, "name": "Ada", "age": 30, "nickname": None})

    def test_query_serializer_uses_rust_typed_coercion(self):
        parsed = QuerySerializer.parse_query_params({"active": "true", "page": "2", "term": "null"})
        self.assertEqual(parsed["active"], True)
        self.assertEqual(parsed["page"], 2)
        self.assertEqual(parsed["page_size"], 20)
        self.assertIsNone(parsed["term"])

    def test_schema_query_uses_rust_coercion(self):
        parsed = QuerySchema.validate_query({"page": "3", "active": "1"})
        self.assertEqual(parsed["page"], 3)
        self.assertEqual(parsed["active"], True)

    def test_alias_and_source(self):
        serializer = AliasNestedSerializer(data={"displayName": "Ada", "profile": {"city": "Kyiv"}})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["name"], "Ada")
        self.assertEqual(serializer.validated_data["profile_data"]["city"], "Kyiv")

    def test_nested_output(self):
        serializer = AliasNestedSerializer(instance={"name": "Ada", "profile_data": {"city": "Kyiv"}})
        self.assertEqual(serializer.data["displayName"], "Ada")
        self.assertEqual(serializer.data["profile"]["city"], "Kyiv")

    def test_async_query_contract_on_api(self):
        app = API()

        @app.get("/search", query_schema=AsyncQueryContract)
        async def search(request):
            return {"q": request.query_data["q"]}

        status, body = asyncio.run(call_app(app, "GET", "/search?q=fast"))
        self.assertEqual(status, 200)
        self.assertEqual(body["q"], "FAST")


async def call_app(app, method, path):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

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
