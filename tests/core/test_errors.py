from pyferox.errors import HTTPError, error_payload


def test_http_error_attributes():
    exc = HTTPError(422, "validation failed", {"field": "name"})
    assert exc.status_code == 422
    assert exc.message == "validation failed"
    assert exc.details == {"field": "name"}


def test_error_payload_shape():
    payload = error_payload(404, "not found", {"resource": "user"})
    assert payload == {
        "error": {
            "code": 404,
            "message": "not found",
            "details": {"resource": "user"},
        }
    }
