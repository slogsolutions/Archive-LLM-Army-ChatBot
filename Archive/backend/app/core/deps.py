# AUTH MIDDLEWARE | You already have JWT — now centralize it.

from fastapi import Header, HTTPException, Depends
from jose import jwt
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User

SECRET_KEY = "secret"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

        user = db.query(User).filter(User.id == payload["user_id"]).first()

        if not user:
            raise Exception()

        return user

    except:
        raise HTTPException(status_code=401, detail="Invalid token")