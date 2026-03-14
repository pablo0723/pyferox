import json
import asyncio

import pytest
from django.test import RequestFactory

from pyferox.errors import HTTPError
from pyferox.request import Request


def test_from_asgi_collects_body_headers_query():
    chunks = [
        {"type": "http.request", "body": b'{"a":', "more_body": True},
        {"type": "http.request", "body": b'1}', "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    req = asyncio.run(
        Request.from_asgi(
            scope={
                "method": "post",
                "path": "/x",
                "headers": [(b"content-type", b"application/json")],
                "query_string": b"q=abc&x=1&x=2",
            },
            receive=receive,
            path_params={"id": "1"},
        )
    )
    assert req.method == "POST"
    assert req.path == "/x"
    assert req.headers["content-type"] == "application/json"
    assert req.query_params == {"q": "abc", "x": "2"}
    assert req.path_params == {"id": "1"}
    assert req.json_body == {"a": 1}


def test_from_django_maps_request():
    rf = RequestFactory()
    dj_req = rf.post("/api/users?limit=3", data=json.dumps({"name": "Ada"}), content_type="application/json")
    dj_req.user = "u1"
    wrapped = Request.from_django(dj_req, {"user_id": "1"})
    assert wrapped.method == "POST"
    assert wrapped.path == "/api/users"
    assert wrapped.query_params["limit"] == "3"
    assert wrapped.path_params["user_id"] == "1"
    assert wrapped.user == "u1"
    assert wrapped.json_body["name"] == "Ada"


def test_json_body_invalid_json():
    req = Request("POST", "/x", {}, {}, {}, body=b"{bad")
    with pytest.raises(HTTPError) as exc:
        _ = req.json_body
    assert exc.value.status_code == 400


def test_json_body_non_object():
    req = Request("POST", "/x", {}, {}, {}, body=b"[1,2]")
    with pytest.raises(HTTPError) as exc:
        _ = req.json_body
    assert exc.value.status_code == 400


def test_json_and_query_aliases():
    req = Request("POST", "/x", {}, {"a": "1"}, {}, body=b'{"k":"v"}')
    req._query_cache = {"a": 1}
    assert req.data == {"k": "v"}
    assert req.query_data == {"a": 1}


def test_query_data_fallback_to_query_params():
    req = Request("GET", "/x", {}, {"a": "1"}, {}, body=b"")
    assert req.query_data == {"a": "1"}


def test_from_asgi_ignores_non_http_request_messages():
    async def receive():
        if not hasattr(receive, "step"):
            receive.step = 0
        receive.step += 1
        if receive.step == 1:
            return {"type": "lifespan.startup"}
        return {"type": "http.request", "body": b"{}", "more_body": False}

    req = asyncio.run(
        Request.from_asgi(
            scope={"method": "GET", "path": "/x", "headers": [], "query_string": b""},
            receive=receive,
            path_params={},
        )
    )
    assert req.json_body == {}
