import os

from fastapi import Request, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models.user import User
from .db import get_db

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    if os.getenv("ENVIRONMENT", "dev") == "dev":
        cognito_sub = os.getenv("LOCAL_DEV_COGNITO_SUB", "local-dev-user")
    else:
        claims = request.scope["aws.event"]["requestContext"]["authorizer"]["jwt"]["claims"]
        cognito_sub = claims.get("sub")
        if not cognito_sub:
            raise HTTPException(status_code=401, detail="Missing User Identity")

    user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
    if not user:
        user = User(cognito_sub=cognito_sub)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
        else:
            db.refresh(user)
    return user
