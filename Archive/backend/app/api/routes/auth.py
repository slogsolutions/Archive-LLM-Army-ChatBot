from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User
from app.services.auth_service import verify_password, create_token
from app.core.deps import get_current_user
from app.schemas.auth_schema import UserLogin


# audiut import 
from app.core.audit import audit_action

# LOGGER 
from app.core.logger import logger

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/login")
@audit_action("USER_LOGGED_IN")
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.army_number == data.army_number).first()

    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    token = create_token({
        "user_id": user.id,
        "role": user.role
    })

    return {"access_token": token}


@router.get("/me")
@audit_action("USER_PROFILE")
def me(user=Depends(get_current_user)):
    return {
        "id": user.id,
        "army_number": user.army_number,
        "name": user.name,
        "role": user.role,
        "rank_level": user.rank_level,
        "hq_id": user.hq_id,
        "unit_id": user.unit_id,
        "branch_id": user.branch_id,
        "clerk_type": user.clerk_type,
        "task_category": user.task_category,
    }
