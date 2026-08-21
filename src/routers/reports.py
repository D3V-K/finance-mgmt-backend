from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..dependencies import get_current_user
from ..db import get_db
from ..models.category import Category, CategoryType
from ..models.transaction import Transaction
from ..models.user import User
from ..schemas.report import CategoryReport, MonthlyReport, NetWorthPoint

router = APIRouter(prefix="/reports", tags=["reports"])


def _apply_date_range(query, column, from_: date | None, to: date | None):
    if from_ is not None:
        query = query.filter(column >= from_)
    if to is not None:
        query = query.filter(column <= to)
    return query


@router.get("/monthly", response_model=list[MonthlyReport])
def monthly_report(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = func.date_trunc("month", Transaction.transaction_date).label("month")
    income = func.sum(
        case((Category.type == CategoryType.INCOME, Transaction.amount), else_=0)
    ).label("income")
    expense = func.sum(
        case((Category.type == CategoryType.EXPENSE, Transaction.amount), else_=0)
    ).label("expense")

    query = (
        db.query(month, income, expense)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Transaction.user_id == user.id)
    )
    query = _apply_date_range(query, Transaction.transaction_date, from_, to)
    rows = query.group_by(month).order_by(month).all()

    return [
        MonthlyReport(month=row.month.date(), income=int(row.income or 0), expense=int(row.expense or 0))
        for row in rows
    ]


@router.get("/by-category", response_model=list[CategoryReport])
def by_category_report(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = func.sum(Transaction.amount).label("total")

    query = (
        db.query(
            Category.id.label("category_id"),
            Category.name.label("category_name"),
            total,
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(Transaction.user_id == user.id, Category.type == CategoryType.EXPENSE)
    )
    query = _apply_date_range(query, Transaction.transaction_date, from_, to)
    rows = query.group_by(Category.id, Category.name).order_by(total.desc()).all()

    return [
        CategoryReport(category_id=row.category_id, category_name=row.category_name, total=int(row.total or 0))
        for row in rows
    ]


@router.get("/net-worth", response_model=list[NetWorthPoint])
def net_worth_report(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = func.date_trunc("month", Transaction.transaction_date).label("month")
    net = func.sum(
        case(
            (Category.type == CategoryType.INCOME, Transaction.amount),
            else_=-Transaction.amount,
        )
    ).label("net")

    monthly_totals = (
        db.query(month, net)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Transaction.user_id == user.id)
        .group_by(month)
        .subquery()
    )

    cumulative = func.sum(monthly_totals.c.net).over(order_by=monthly_totals.c.month).label("net_worth")
    outer = db.query(monthly_totals.c.month.label("month"), cumulative).subquery()

    query = db.query(outer.c.month, outer.c.net_worth)
    query = _apply_date_range(query, outer.c.month, from_, to)
    rows = query.order_by(outer.c.month).all()

    return [NetWorthPoint(month=row.month.date(), net_worth=int(row.net_worth)) for row in rows]
