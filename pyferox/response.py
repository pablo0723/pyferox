from __future__ import annotations

from dataclasses import dataclass, field

from .rust_bridge import serialize_json


@dataclass
class Response:
    body: bytes = b""
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def as_asgi(self):
        headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in self.headers.items()]
        return self.status_code, headers, self.body


class JSONResponse(Response):
    def __init__(self, data, status_code: int = 200, headers: dict[str, str] | None = None):
        payload = serialize_json(data)
        merged = {"content-type": "application/json"}
        if headers:
            merged.update(headers)
        super().__init__(body=payload.encode("utf-8"), status_code=status_code, headers=merged)


def ensure_response(value):
    if isinstance(value, Response):
        return value
    if isinstance(value, bytes):
        return Response(value, headers={"content-type": "application/octet-stream"})
    if isinstance(value, str):
        return Response(value.encode("utf-8"), headers={"content-type": "text/plain; charset=utf-8"})
    return JSONResponse(value)
