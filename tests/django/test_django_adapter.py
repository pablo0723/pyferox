import asyncio
import json

from django.test import AsyncRequestFactory

from pyferox.django.adapter import _to_asgi_scope, as_django_view


def _run(view, request):
    return asyncio.run(view(request))


def test_adapter_happy_path():
    # use django adapter on top of already django-driven API still should work with ASGI bridge contract
    async def asgi_like(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    view = as_django_view(asgi_like)
    req = AsyncRequestFactory().get("/x")
    resp = _run(view, req)
    assert resp.status_code == 200
    assert json.loads(resp.content.decode("utf-8")) == {"ok": True}


def test_adapter_disconnect_and_headers_mapping():
    captured = {"count": 0}

    async def app(scope, receive, send):
        msg1 = await receive()
        msg2 = await receive()
        captured["count"] = 2
        assert msg1["type"] == "http.request"
        assert msg2["type"] == "http.disconnect"
        assert scope["method"] == "GET"
        assert scope["path"] == "/x"
        await send({"type": "http.response.start", "status": 204, "headers": [(b"x-a", b"b")]})
        await send({"type": "http.response.body", "body": b""})

    view = as_django_view(app)
    req = AsyncRequestFactory().get("/x?y=1", HTTP_X_T="1")
    resp = _run(view, req)
    assert captured["count"] == 2
    assert resp.status_code == 204
    assert resp.headers["x-a"] == "b"


def test_to_asgi_scope_includes_content_headers():
    req = AsyncRequestFactory().post("/x?y=1", data='{"a":1}', content_type="application/json")
    scope = _to_asgi_scope(req)
    assert scope["method"] == "POST"
    assert scope["path"] == "/x"
    assert scope["query_string"] == b"y=1"
    header_names = {name for name, _ in scope["headers"]}
    assert b"content-type" in header_names
    assert b"content-length" in header_names
