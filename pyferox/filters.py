from __future__ import annotations


class BaseFilterBackend:
    def filter_queryset(self, request, queryset, view):
        return queryset


class FieldFilterBackend(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        fields = getattr(view, "filterset_fields", []) or []
        if not fields:
            return queryset
        out = list(queryset)
        for field in fields:
            if field not in request.query_params:
                continue
            expected = request.query_params[field]
            out = [item for item in out if str(_value(item, field)) == expected]
        return out


class SearchFilter(BaseFilterBackend):
    search_param = "search"

    def filter_queryset(self, request, queryset, view):
        term = request.query_params.get(self.search_param, "")
        if not term:
            return queryset
        term = term.lower()
        fields = getattr(view, "search_fields", []) or []
        if not fields:
            return queryset
        out = []
        for item in queryset:
            for field in fields:
                if term in str(_value(item, field, "")).lower():
                    out.append(item)
                    break
        return out


class OrderingFilter(BaseFilterBackend):
    ordering_param = "ordering"

    def filter_queryset(self, request, queryset, view):
        ordering = request.query_params.get(self.ordering_param)
        if not ordering:
            return queryset
        field = ordering
        reverse = False
        if ordering.startswith("-"):
            field = ordering[1:]
            reverse = True
        allowed = getattr(view, "ordering_fields", []) or []
        if allowed and field not in allowed:
            return queryset
        return sorted(queryset, key=lambda item: _value(item, field), reverse=reverse)


def _value(item, field, default=None):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)
