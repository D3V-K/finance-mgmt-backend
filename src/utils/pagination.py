import math
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Query as SQLAlchemyQuery


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

ItemT = TypeVar("ItemT")


class PaginationParams:
    """Validated pagination query parameters shared by list endpoints."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_pages: int = Field(ge=0)


def paginate(query: SQLAlchemyQuery, pagination: PaginationParams) -> PaginatedResponse:
    """Count and fetch one page from an already filtered and ordered query."""

    total = query.order_by(None).count()
    items = query.offset(pagination.offset).limit(pagination.page_size).all()
    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=math.ceil(total / pagination.page_size),
    )
