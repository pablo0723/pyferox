from __future__ import annotations


class BasePermission:
    def has_permission(self, request, view) -> bool:
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        return True


class AllowAny(BasePermission):
    pass


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view) -> bool:
        return getattr(request, "user", None) is not None
