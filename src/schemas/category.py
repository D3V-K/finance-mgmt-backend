import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from ..models.category import CategoryType


class CategoryBase(BaseModel):
    name: str
    type: CategoryType
    color: str | None = None
    parent_id: uuid.UUID | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = None
    type: CategoryType | None = None
    color: str | None = None
    parent_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> "CategoryUpdate":
        non_nullable_fields = ("name", "type")
        nulled = [
            field
            for field in non_nullable_fields
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if nulled:
            raise ValueError(f"Fields cannot be null: {', '.join(nulled)}")
        return self


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime


class CategoryTreeRead(CategoryRead):
    children: list["CategoryTreeRead"] = []


CategoryTreeRead.model_rebuild()
