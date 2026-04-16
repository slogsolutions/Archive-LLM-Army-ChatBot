from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.branch import Branch
from app.core.deps import get_current_user, get_db

router = APIRouter()


@router.post("/create")
def create_branch(data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):

    if user.role not in ["super_admin", "hq_admin", "unit_admin"]:
        raise HTTPException(403, "Not allowed")

    # Unit Admin restriction
    if user.role == "unit_admin" and user.unit_id != data.get("unit_id"):
        raise HTTPException(403, "Wrong unit")

    branch = Branch(
        name=data.get("name"),
        description=data.get("description"),
        unit_id=data.get("unit_id")
    )

    db.add(branch)
    db.commit()

    return {"message": "Branch created"}