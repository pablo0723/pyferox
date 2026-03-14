import asyncio
import json
import unittest

from pyferox import API, HTTPError, Schema


class CreateIn(Schema):
    name: str
    age: int


class CreateOut(Schema):
    id: int
    name: str
    age: int


app = API()


@app.post("/users", input_schema=CreateIn, output_schema=CreateOut)
async def create_user(request):
    payload = request.json_body
    if payload["age"] < 0:
        raise HTTPError(422, "age must be >= 0")
    return {"id": 7, "name": payload["name"], "age": payload["age"]}


class SmokeTest(unittest.TestCase):
    def test_post_valid(self):
        status, body = asyncio.run(call_app("POST", "/users", {"name": "Ada", "age": 33}))
        self.assertEqual(status, 200)
        self.assertEqual(body["id"], 7)
        self.assertEqual(body["name"], "Ada")

    def test_post_validation_error(self):
        status, body = asyncio.run(call_app("POST", "/users", {"name": "Ada", "age": "oops"}))
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], 422)

    def test_post_json_error(self):
        status, body = asyncio.run(call_app_raw("POST", "/users", b"{not-json"))
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], 400)

    def test_not_found(self):
        status, body = asyncio.run(call_app("GET", "/nope", {}))
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], 404)


async def call_app(method, path, payload):
    return await call_app_raw(method, path, json.dumps(payload).encode("utf-8"))


async def call_app_raw(method, path, body):
    sent = []

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
