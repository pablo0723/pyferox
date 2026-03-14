from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs

from .errors import HTTPError


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str]
    query_params: dict[str, str]
    path_params: dict[str, str]
    body: bytes = b""
    user: object | None = None
    auth: object | None = None
    _json_cache: dict | None = field(default=None, init=False, repr=False)
    _query_cache: dict | None = field(default=None, init=False, repr=False)

    @classmethod
    async def from_asgi(cls, scope, receive, path_params: dict[str, str]):
        body = b""
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        raw_headers = scope.get("headers", [])
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw_headers}
        query = scope.get("query_string", b"").decode("utf-8")
        query_params = {k: values[-1] for k, values in parse_qs(query, keep_blank_values=True).items()}
        return cls(
            method=scope["method"].upper(),
            path=scope["path"],
            headers=headers,
            query_params=query_params,
            path_params=path_params,
            body=body,
        )

    @property
    def json_body(self):
        if self._json_cache is not None:
            return self._json_cache
        if not self.body:
            self._json_cache = {}
            return self._json_cache
        try:
            parsed = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPError(400, "invalid JSON body", {"reason": str(exc)}) from exc
        if not isinstance(parsed, dict):
            raise HTTPError(400, "JSON body must be an object")
        self._json_cache = parsed
        return parsed

    @property
    def data(self):
        return self.json_body

    @property
    def query_data(self):
        if self._query_cache is not None:
            return self._query_cache
        return self.query_params
