"""Pagination and list-query primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pyferox.core.messages import Query


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(slots=True)
class SortField:
    field: str
    direction: SortDirection = SortDirection.ASC


@dataclass(slots=True)
class PageParams:
    page: int = 1
    page_size: int = 20

    def normalized(self, *, max_page_size: int = 100) -> "PageParams":
        page = max(self.page, 1)
        page_size = max(min(self.page_size, max_page_size), 1)
        return PageParams(page=page, page_size=page_size)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(slots=True)
class ListQuery(Query):
    page: PageParams = field(default_factory=PageParams)
    filters: dict[str, Any] = field(default_factory=dict)
    sorts: list[SortField] = field(default_factory=list)


def parse_sort(raw: str) -> list[SortField]:
    items: list[SortField] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token.startswith("-"):
            items.append(SortField(field=token[1:], direction=SortDirection.DESC))
        else:
            items.append(SortField(field=token.lstrip("+"), direction=SortDirection.ASC))
    return items


def build_page_params(*, page: int | None, page_size: int | None) -> PageParams:
    params = PageParams(page=page or 1, page_size=page_size or 20)
    return params.normalized()

