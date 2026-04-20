from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services.auth_service import hash_password

router = APIRouter()


# =========================
# CREATE USER
# =========================

@router.post("/create")
def create_user(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    role = data.get("role")
    if not role:
        raise HTTPException(400, "Role is required")

    # 🔥 ROLE CONTROL
    if current_user.role == "super_admin":
        pass

    elif current_user.role == "hq_admin":
        if role not in ["unit_admin", "officer", "clerk", "trainee"]:
            raise HTTPException(403, "Not allowed role")
        if current_user.hq_id != data.get("hq_id"):
            raise HTTPException(403, "Wrong HQ")

    elif current_user.role == "unit_admin":
        if role not in ["officer", "clerk", "trainee"]:
            raise HTTPException(403, "Not allowed role")
        if current_user.unit_id != data.get("unit_id"):
            raise HTTPException(403, "Wrong Unit")

    else:
        raise HTTPException(403, "Not allowed")

    if not data.get("army_number"):
        raise HTTPException(400, "Army number is required")

    if not data.get("name"):
        raise HTTPException(400, "Name is required")

    # Duplicate army number check
    existing = db.query(User).filter(User.army_number == data.get("army_number")).first()
    if existing:
        raise HTTPException(400, "Army number already exists")

    # 🔥 Clerk logic
    clerk_type = data.get("clerk_type")
    task_category = data.get("task_category")

    if role != "clerk":
        clerk_type = None
        task_category = None
    else:
        if clerk_type not in ["junior", "senior"]:
            raise HTTPException(400, "clerk_type must be junior or senior")

    new_user = User(
        army_number=data.get("army_number"),
        name=data.get("name"),
        password=hash_password(data.get("password")),
        role=role,
        rank_level=data.get("rank_level"),
        hq_id=data.get("hq_id"),
        unit_id=data.get("unit_id"),
        branch_id=data.get("branch_id"),
        clerk_type=clerk_type,
        task_category=task_category
    )

    db.add(new_user)
    db.commit()

    return {"message": "User created"}

# =========================
# GET ALL USERS (SCOPED)
# =========================

@router.get("/")
def get_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role == "super_admin":
        return db.query(User).all()

    if current_user.role == "hq_admin":
        return db.query(User).filter(User.hq_id == current_user.hq_id).all()

    if current_user.role == "unit_admin":
        return db.query(User).filter(User.unit_id == current_user.unit_id).all()

    raise HTTPException(403, "Not allowed")

# =========================
# GET SINGLE USER
# =========================
@router.get("/{user_id}")
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user = db.get(User, user_id)

    if not user:
        raise HTTPException(404, "User not found")

    # simple scope check
    if current_user.role == "hq_admin" and user.hq_id != current_user.hq_id:
        raise HTTPException(403, "Not allowed")

    if current_user.role == "unit_admin" and user.unit_id != current_user.unit_id:
        raise HTTPException(403, "Not allowed")

    return user


# =========================
# UPDATE USER
# =========================

@router.put("/update/{user_id}")
def update_user(
    user_id: int,
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    if current_user.rank_level >= user.rank_level:
        raise HTTPException(403, "Cannot modify equal/higher user")

    if current_user.role == "hq_admin" and user.hq_id != current_user.hq_id:
        raise HTTPException(403, "Wrong HQ")

    if current_user.role == "unit_admin" and user.unit_id != current_user.unit_id:
        raise HTTPException(403, "Wrong Unit")

    allowed_fields = [
        "army_number", "name", "password", "role", "rank_level",
        "hq_id", "unit_id", "branch_id",
        "task_category", "clerk_type"
    ]

    for key in allowed_fields:
        if key in data:
            value = data[key]
            if key == "password":
                setattr(user, key, hash_password(value))
            else:
                setattr(user, key, value)

    # 🔥 Clerk logic
    if user.role != "clerk":
        user.clerk_type = None
        user.task_category = None
    else:
        if user.clerk_type not in ["junior", "senior"]:
            raise HTTPException(400, "Invalid clerk_type")

    db.commit()

    return {"message": "User updated"}
# =========================
# DELETE USER
# =========================
@router.delete("/delete/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user = db.get(User, user_id)

    if not user:
        raise HTTPException(404, "User not found")

    # 🔥 Rank check
    if current_user.rank_level >= user.rank_level:
        raise HTTPException(403, "Cannot delete equal/higher user")

    # Scope validation
    if current_user.role == "hq_admin" and user.hq_id != current_user.hq_id:
        raise HTTPException(403, "Wrong HQ")

    if current_user.role == "unit_admin" and user.unit_id != current_user.unit_id:
        raise HTTPException(403, "Wrong Unit")

    db.delete(user)
    db.commit()

    return {"message": "User deleted"}
