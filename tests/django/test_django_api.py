import asyncio
import json

import pytest
from django.test import AsyncRequestFactory

from pyferox import API, Field, HTTPError, Serializer
from pyferox.django.api import _django_pattern, _replace_path_params


class InSerializer(Serializer):
    name: str
    age: int = Field(required=False, default=18)


class OutSerializer(Serializer):
    id: int
    name: str
    age: int


class QuerySerializer(Serializer):
    limit: int = Field(required=False, default=10)


def _run(view, request, **kwargs):
    return asyncio.run(view(request, **kwargs))


def test_django_api_get_with_query_and_output_contract():
    app = API(prefix="api")

    @app.get("users/{user_id}", query_schema=QuerySerializer, output_schema=OutSerializer)
    async def get_user(request):
        if request.path_params["user_id"] != "1":
            raise HTTPError(404, "not found")
        return {"id": 1, "name": "Ada", "age": request.query_data["limit"]}

    route = app.urls[0]
    req = AsyncRequestFactory().get("/api/users/1?limit=5")
    resp = _run(route.callback, req, user_id="1")
    assert resp.status_code == 200
    body = json.loads(resp.content.decode("utf-8"))
    assert body == {"id": 1, "name": "Ada", "age": 5}


def test_django_api_post_input_contract_and_error():
    app = API(prefix="api")

    @app.post("users", input_schema=InSerializer)
    async def create_user(request):
        return request.data

    route = app.urls[0]
    req_ok = AsyncRequestFactory().post("/api/users", data=json.dumps({"name": "Ada"}), content_type="application/json")
    resp_ok = _run(route.callback, req_ok)
    assert json.loads(resp_ok.content.decode("utf-8"))["age"] == 18

    req_bad = AsyncRequestFactory().post("/api/users", data=json.dumps({"age": "x"}), content_type="application/json")
    resp_bad = _run(route.callback, req_bad)
    assert resp_bad.status_code == 422


def test_django_api_wrong_method():
    app = API()

    @app.get("health")
    async def health(request):
        return {"ok": True}

    req = AsyncRequestFactory().post("/health", data=b"", content_type="application/json")
    resp = _run(app.urls[0].callback, req)
    assert resp.status_code == 405


def test_django_api_unhandled_exception_to_500():
    app = API()

    @app.get("boom")
    async def boom(request):
        raise RuntimeError("boom")

    req = AsyncRequestFactory().get("/boom")
    resp = _run(app.urls[0].callback, req)
    assert resp.status_code == 500


def test_django_api_contract_type_errors():
    with pytest.raises(TypeError):
        asyncio.run(apply_contract_bad_input())
    with pytest.raises(TypeError):
        asyncio.run(apply_contract_bad_output())
    with pytest.raises(TypeError):
        asyncio.run(apply_contract_bad_query())


async def apply_contract_bad_input():
    from pyferox.django.api import _apply_input_contract

    await _apply_input_contract(object(), {"a": 1})


async def apply_contract_bad_output():
    from pyferox.django.api import _apply_output_contract

    await _apply_output_contract(object(), {"a": 1})


async def apply_contract_bad_query():
    from pyferox.django.api import _apply_query_contract

    await _apply_query_contract(object(), {"a": "1"})


def test_django_pattern_helpers():
    assert _replace_path_params("users/{id}/posts/{post_id}") == "users/<str:id>/posts/<str:post_id>"
    assert _django_pattern("api", "/users/{id}/") == "api/users/<str:id>"
    assert _django_pattern("api", "") == "api"


def test_django_api_put_patch_delete_helpers():
    app = API(prefix="v1")

    @app.put("x")
    async def put_x(request):
        return {"m": "put"}

    @app.patch("y")
    async def patch_y(request):
        return {"m": "patch"}

    @app.delete("z")
    async def delete_z(request):
        return {"m": "delete"}

    assert [u.pattern._route for u in app.urls] == ["v1/x", "v1/y", "v1/z"]


def test_contract_custom_validate_paths():
    class AsyncIn:
        @staticmethod
        async def validate(payload):
            return {"x": int(payload["x"])}

    class AsyncOut:
        @staticmethod
        async def validate(payload):
            return {"wrapped": payload}

    class AsyncQuery:
        @staticmethod
        async def validate_query(payload):
            return {"x": int(payload["x"])}

    app = API()

    @app.post("custom", input_schema=AsyncIn, output_schema=AsyncOut, query_schema=AsyncQuery)
    async def custom(request):
        return request.data["x"] + request.query_data["x"]

    req = AsyncRequestFactory().post("/custom?x=2", data=json.dumps({"x": 3}), content_type="application/json")
    resp = _run(app.urls[0].callback, req)
    assert resp.status_code == 200
    body = json.loads(resp.content.decode("utf-8"))
    assert body == {"wrapped": 5}
