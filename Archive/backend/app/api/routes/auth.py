from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from jose import jwt

from app.core.database import SessionLocal
from app.models.user import User
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_token,
)
from app.core.config import SECRET_KEY
from app.schemas.auth_schema import UserCreate, UserLogin

router = APIRouter()


# 🔹 DB Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ✅ REGISTER
@router.post("/register")
def register(data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(
        email=data.email,
        password=hash_password(data.password),
        role="admin", #fix this from role to dynamic REMEMBER
        rank_level=1,
    )

    db.add(new_user)
    db.commit()

    return {"message": "User created"}


# ✅ LOGIN
@router.post("/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid password")

    token = create_token({
        "user_id": user.id,
        "role": user.role
    })

    return {"access_token": token}


# ✅ GET CURRENT USER
@router.get("/me")
def get_me(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    try:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid auth header")

        token = authorization.split(" ")[1]

        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": user.id,
            "email": user.email,
            "role": user.role
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")