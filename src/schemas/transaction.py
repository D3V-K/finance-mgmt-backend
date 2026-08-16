import uuid
from datetime import date as date_type, datetime

from pydantic import BaseModel, ConfigDict, model_validator


class TransactionBase(BaseModel):
    amount: int
    description: str | None = None
    category_id: uuid.UUID
    transaction_date: date_type


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    amount: int | None = None
    description: str | None = None
    category_id: uuid.UUID | None = None
    transaction_date: date_type | None = None

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> "TransactionUpdate":
        non_nullable_fields = ("amount", "category_id", "transaction_date")
        nulled = [
            field
            for field in non_nullable_fields
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if nulled:
            raise ValueError(f"Fields cannot be null: {', '.join(nulled)}")
        return self


class TransactionRead(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
