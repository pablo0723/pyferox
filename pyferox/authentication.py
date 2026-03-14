from __future__ import annotations


class BaseAuthentication:
    def authenticate(self, request):
        return None


class TokenAuthentication(BaseAuthentication):
    keyword = "token"

    def authenticate(self, request):
        header = request.headers.get("authorization", "")
        if not header:
            return None
        parts = header.split(None, 1)
        if len(parts) != 2:
            return None
        scheme, token = parts
        if scheme.lower() != self.keyword:
            return None
        user = {"id": token, "is_authenticated": True}
        return user, token
