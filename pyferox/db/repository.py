"""Repository base abstractions."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

TEntity = TypeVar("TEntity")
TId = TypeVar("TId")


class Repository(Generic[TEntity, TId]):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

