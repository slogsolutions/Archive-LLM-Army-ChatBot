from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services.auth_service import hash_password

router = APIRouter()

# audiut import 
from app.core.audit import audit_action

# LOGGER 
from app.core.logger import logger

router = APIRouter()




# =========================
# CREATE USER
# =========================


@router.post("/create")
@audit_action("CREATE_USER")
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
    db.refresh(new_user)

    return {"message": f"User '{new_user.name}' ({new_user.role}) created", "id": new_user.id}

def _safe_user(u: User) -> dict:
    return {
        "id": u.id,
        "army_number": u.army_number,
        "name": u.name,
        "role": u.role,
        "rank_level": u.rank_level,
        "hq_id": u.hq_id,
        "unit_id": u.unit_id,
        "branch_id": u.branch_id,
        "clerk_type": u.clerk_type,
        "task_category": u.task_category,
    }


# =========================
# GET ALL USERS (SCOPED)
# =========================

@router.get("/")
@audit_action("GET_ALL_USER")
def get_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role == "super_admin":
        return [_safe_user(u) for u in db.query(User).all()]

    if current_user.role == "hq_admin":
        return [_safe_user(u) for u in db.query(User).filter(User.hq_id == current_user.hq_id).all()]

    if current_user.role == "unit_admin":
        return [_safe_user(u) for u in db.query(User).filter(User.unit_id == current_user.unit_id).all()]

    raise HTTPException(403, "Not allowed")

# =========================
# GET SINGLE USER
# =========================


@router.get("/{user_id}")
@audit_action("GET_SINGLE_USER")
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    user = db.get(User, user_id)

    if not user:
        raise HTTPException(404, "User not found")

    if current_user.role == "hq_admin" and user.hq_id != current_user.hq_id:
        raise HTTPException(403, "Not allowed")

    if current_user.role == "unit_admin" and user.unit_id != current_user.unit_id:
        raise HTTPException(403, "Not allowed")

    return _safe_user(user)


# =========================
# UPDATE USER
# =========================


@router.put("/update/{user_id}")
@audit_action("UDPATE_USER")
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
# QUICK ROLE / RANK PATCH
# =========================
@router.patch("/access/{user_id}")
@audit_action("UPDATE_USER_ACCESS")
def patch_user_access(
    user_id: int,
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Quick patch for role and/or rank_level only.
    Used by the RBAC management UI for inline edits.
    """
    if current_user.role not in ["super_admin", "hq_admin", "unit_admin"]:
        raise HTTPException(403, "Not allowed")

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")

    # Cannot modify a user at same or higher rank
    if current_user.rank_level >= target.rank_level:
        raise HTTPException(403, "Cannot modify a user at equal or higher rank")

    # Scope check
    if current_user.role == "hq_admin" and target.hq_id != current_user.hq_id:
        raise HTTPException(403, "Out of HQ scope")
    if current_user.role == "unit_admin" and target.unit_id != current_user.unit_id:
        raise HTTPException(403, "Out of unit scope")

    ALLOWED_ROLES = {
        "super_admin": ["super_admin", "hq_admin", "unit_admin", "officer", "clerk", "trainee"],
        "hq_admin":    ["unit_admin", "officer", "clerk", "trainee"],
        "unit_admin":  ["officer", "clerk", "trainee"],
    }

    if "role" in data:
        new_role = data["role"]
        if new_role not in ALLOWED_ROLES.get(current_user.role, []):
            raise HTTPException(403, f"Cannot assign role '{new_role}'")
        target.role = new_role
        # Clear clerk-specific fields when switching away from clerk
        if new_role != "clerk":
            target.clerk_type = None
            target.task_category = None

    if "rank_level" in data:
        new_rank = int(data["rank_level"])
        if not (1 <= new_rank <= 6):
            raise HTTPException(400, "rank_level must be 1–6")
        # Cannot promote target above current user's own rank
        if new_rank < current_user.rank_level:
            raise HTTPException(403, "Cannot promote above your own rank level")
        target.rank_level = new_rank

    db.commit()
    return {"message": "Access updated", "role": target.role, "rank_level": target.rank_level}


# =========================
# DELETE USER
# =========================


@router.delete("/delete/{user_id}")
@audit_action("DELETE_USER")
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
