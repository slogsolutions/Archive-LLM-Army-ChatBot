from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.hq import HeadQuarter

router = APIRouter()


@router.post("/create")
def create_hq(data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):

    if user.role != "super_admin":
        raise HTTPException(403, "Only super admin allowed")

    hq = HeadQuarter(name=data.get("name"))
    db.add(hq)
    db.commit()

    return {"message": "HQ created"}