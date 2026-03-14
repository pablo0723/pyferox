import asyncio
import json
import unittest
from dataclasses import dataclass

from pyferox import API, ModelSerializer, Serializer


class CreateUserSerializer(Serializer):
    name: str
    age: int


@dataclass
class UserModel:
    id: int
    name: str
    age: int


class UserModelSerializer(ModelSerializer):
    class Meta:
        model = UserModel
        fields = ["id", "name", "age"]


app = API()


@app.post("/drf-users", input_schema=CreateUserSerializer, output_schema=UserModelSerializer)
def create_user(request):
    payload = request.data
    return UserModel(id=10, name=payload["name"], age=payload["age"])


class DRFStyleTests(unittest.TestCase):
    def test_serializer_validation_like_drf(self):
        serializer = CreateUserSerializer(data={"name": "Ada", "age": 33})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["name"], "Ada")

    def test_model_serializer_data(self):
        user = UserModel(id=1, name="Ada", age=33)
        serializer = UserModelSerializer(instance=user)
        self.assertEqual(serializer.data, {"id": 1, "name": "Ada", "age": 33})

    def test_route_with_serializer_contract(self):
        status, body = asyncio.run(call_app("POST", "/drf-users", {"name": "Ada", "age": 33}))
        self.assertEqual(status, 200)
        self.assertEqual(body["id"], 10)
        self.assertEqual(body["name"], "Ada")

    def test_route_validation_error(self):
        status, body = asyncio.run(call_app("POST", "/drf-users", {"name": "Ada", "age": "bad"}))
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], 422)


async def call_app(method, path, payload):
    sent = []
    body = json.dumps(payload).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }
    await app(scope, receive, send)
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    body_bytes = next(item["body"] for item in sent if item["type"] == "http.response.body")
    return status, json.loads(body_bytes.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
