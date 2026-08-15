import os

from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from .models.user import User
from .db import get_db

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    if os.getenv("ENVIRONMENT", "dev") != "prod":
        cognito_sub = os.getenv("LOCAL_DEV_COGNITO_SUB", "local-dev-user")
    else:
        claims = request.state.aws_event["requestContext"]["authorizer"]["jwt"]["claims"]
        cognito_sub = claims.get("sub")
        if not cognito_sub:
            raise HTTPException(status_code=401, detail="Missing User Identity")

        user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
        if not user:
            user = User(cognito_sub=cognito_sub)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
