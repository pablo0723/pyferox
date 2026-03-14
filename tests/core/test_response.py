from pyferox.response import JSONResponse, Response, ensure_response


def test_response_asgi_format():
    resp = Response(body=b"ok", status_code=201, headers={"X-A": "b"})
    status, headers, body = resp.as_asgi()
    assert status == 201
    assert body == b"ok"
    assert (b"x-a", b"b") in headers


def test_json_response_content_type_and_body():
    resp = JSONResponse({"a": 1})
    status, headers, body = resp.as_asgi()
    assert status == 200
    assert (b"content-type", b"application/json") in headers
    assert body == b'{"a":1}'


def test_ensure_response_variants():
    assert isinstance(ensure_response(Response()), Response)
    assert ensure_response("ok").headers["content-type"].startswith("text/plain")
    assert ensure_response(b"bin").headers["content-type"] == "application/octet-stream"
    assert ensure_response({"x": 1}).headers["content-type"] == "application/json"
