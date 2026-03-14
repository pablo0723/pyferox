from __future__ import annotations

from django.http import HttpResponse


def as_django_view(api_app):
    async def view(request, *args, **kwargs):
        body = request.body
        scope = _to_asgi_scope(request)
        sent = []
        received = False

        async def receive():
            nonlocal received
            if received:
                return {"type": "http.disconnect"}
            received = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            sent.append(message)

        await api_app(scope, receive, send)
        status = 500
        headers = {}
        chunks = []
        for message in sent:
            msg_type = message.get("type")
            if msg_type == "http.response.start":
                status = message["status"]
                for raw_name, raw_value in message.get("headers", []):
                    name = raw_name.decode("latin-1")
                    value = raw_value.decode("latin-1")
                    headers[name] = value
            elif msg_type == "http.response.body":
                chunks.append(message.get("body", b""))
        return HttpResponse(b"".join(chunks), status=status, headers=headers)

    return view


def _to_asgi_scope(request):
    headers = []
    for key, value in request.META.items():
        if key.startswith("HTTP_"):
            name = key[5:].replace("_", "-").lower().encode("latin-1")
            headers.append((name, str(value).encode("latin-1")))
    content_type = request.META.get("CONTENT_TYPE")
    if content_type:
        headers.append((b"content-type", str(content_type).encode("latin-1")))
    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        headers.append((b"content-length", str(content_length).encode("latin-1")))
    return {
        "type": "http",
        "method": request.method.upper(),
        "path": request.path,
        "query_string": request.META.get("QUERY_STRING", "").encode("utf-8"),
        "headers": headers,
    }
