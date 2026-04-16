from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.unit import Unit
from app.core.deps import get_current_user, get_db

router = APIRouter()


@router.post("/create")
def create_unit(data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):

    if user.role not in ["super_admin", "hq_admin"]:
        raise HTTPException(403, "Not allowed")

    # HQ Admin can only create inside own HQ
    if user.role == "hq_admin" and user.hq_id != data.get("hq_id"):
        raise HTTPException(403, "Wrong HQ")

    unit = Unit(
        name=data.get("name"),
        hq_id=data.get("hq_id")
    )

    db.add(unit)
    db.commit()

    return {"message": "Unit created"}