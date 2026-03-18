from __future__ import annotations

from pyferox.core.pagination import PageParams, SortDirection, build_page_params, parse_sort


def test_page_params_normalization_and_offset() -> None:
    params = PageParams(page=0, page_size=500).normalized(max_page_size=100)
    assert params.page == 1
    assert params.page_size == 100
    assert params.offset == 0


def test_parse_sort_supports_direction_prefixes() -> None:
    fields = parse_sort("-created_at,+name")
    assert fields[0].field == "created_at"
    assert fields[0].direction == SortDirection.DESC
    assert fields[1].field == "name"
    assert fields[1].direction == SortDirection.ASC


def test_build_page_params_defaults() -> None:
    params = build_page_params(page=None, page_size=None)
    assert params.page == 1
    assert params.page_size == 20

