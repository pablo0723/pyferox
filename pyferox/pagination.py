from __future__ import annotations


class BasePagination:
    def paginate_queryset(self, queryset, request, view=None):
        raise NotImplementedError

    def get_paginated_response(self, data):
        raise NotImplementedError


class PageNumberPagination(BasePagination):
    page_query_param = "page"
    page_size_query_param = "page_size"
    page_size = 20
    max_page_size = 100

    def __init__(self):
        self.count = 0
        self.page = 1
        self.current_page_size = self.page_size

    def paginate_queryset(self, queryset, request, view=None):
        if queryset is None:
            return None
        items = list(queryset)
        self.count = len(items)
        self.page = _safe_positive_int(request.query_params.get(self.page_query_param), default=1)
        requested_size = _safe_positive_int(request.query_params.get(self.page_size_query_param), default=self.page_size)
        self.current_page_size = min(requested_size, self.max_page_size)
        start = (self.page - 1) * self.current_page_size
        end = start + self.current_page_size
        return items[start:end]

    def get_paginated_response(self, data):
        total_pages = max(1, (self.count + self.current_page_size - 1) // self.current_page_size)
        next_page = self.page + 1 if self.page < total_pages else None
        previous_page = self.page - 1 if self.page > 1 else None
        return {
            "count": self.count,
            "page": self.page,
            "page_size": self.current_page_size,
            "next": next_page,
            "previous": previous_page,
            "results": data,
        }


def _safe_positive_int(value, default: int):
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
