import uuid
from datetime import date as date_type, datetime

from pydantic import BaseModel, ConfigDict


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


class TransactionRead(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
