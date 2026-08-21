import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_current_user
from ..db import get_db
from ..models.category import Category
from ..models.user import User
from ..schemas.category import CategoryCreate, CategoryRead, CategoryTreeRead, CategoryUpdate
from ..utils.pagination import PaginatedResponse, PaginationParams, paginate

router = APIRouter(prefix="/categories", tags=["categories"])


def _get_owned_category(category_id: uuid.UUID, user: User, db: Session) -> Category:
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def _validate_parent(parent_id: uuid.UUID | None, category_id: uuid.UUID | None, user: User, db: Session) -> None:
    if parent_id is None:
        return
    if parent_id == category_id:
        raise HTTPException(status_code=400, detail="Category cannot be its own parent")

    parent = db.query(Category).filter(Category.id == parent_id, Category.user_id == user.id).first()
    if not parent:
        raise HTTPException(status_code=400, detail="Parent category not found")

    current = parent
    while current.parent_id is not None:
        if current.parent_id == category_id:
            raise HTTPException(status_code=400, detail="Category cannot be an ancestor of its own parent")
        current = db.query(Category).filter(Category.id == current.parent_id).first()
        if current is None:
            break


@router.get("", response_model=PaginatedResponse[CategoryRead])
def list_categories(
    pagination: PaginationParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Category)
        .filter(Category.user_id == user.id)
        .order_by(Category.created_at.asc(), Category.id.asc())
    )
    return paginate(query, pagination)


@router.get("/tree", response_model=list[CategoryTreeRead])
def list_categories_tree(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Category)
        .filter(Category.user_id == user.id, Category.parent_id.is_(None))
        .all()
    )


@router.post("", response_model=CategoryRead, status_code=201)
def create_category(
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_parent(payload.parent_id, None, user, db)

    category = Category(
        id=uuid.uuid4(),
        name=payload.name,
        type=payload.type,
        color=payload.color,
        parent_id=payload.parent_id,
        user_id=user.id,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = _get_owned_category(category_id, user, db)

    update_data = payload.model_dump(exclude_unset=True)
    if "parent_id" in update_data:
        _validate_parent(update_data["parent_id"], category.id, user, db)

    for field, value in update_data.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = _get_owned_category(category_id, user, db)
    db.delete(category)
    db.commit()
