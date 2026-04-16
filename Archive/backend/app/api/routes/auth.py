from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User
from app.services.auth_service import verify_password, create_token
from app.core.deps import get_current_user

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.get("email")).first()

    if not user or not verify_password(data.get("password"), user.password):
        raise HTTPException(400, "Invalid credentials")

    token = create_token({"user_id": user.id, "role": user.role})

    return {"access_token": token}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user