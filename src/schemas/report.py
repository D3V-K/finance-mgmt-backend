import uuid
from datetime import date

from pydantic import BaseModel


class MonthlyReport(BaseModel):
    month: date
    income: int
    expense: int


class CategoryReport(BaseModel):
    category_id: uuid.UUID
    category_name: str
    total: int


class NetWorthPoint(BaseModel):
    month: date
    net_worth: int
