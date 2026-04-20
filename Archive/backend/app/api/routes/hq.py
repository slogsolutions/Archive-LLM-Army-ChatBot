from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.hq import HeadQuarter
from app.models.unit import Unit

router = APIRouter()


@router.get("/")
def list_hq(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "super_admin":
        return db.query(HeadQuarter).order_by(HeadQuarter.name).all()

    if user.hq_id:
        hq = db.get(HeadQuarter, user.hq_id)
        return [hq] if hq else []

    return []


@router.post("/create")
def create_hq(data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):

    if user.role != "super_admin":
        raise HTTPException(403, "Only super admin allowed")

    hq = HeadQuarter(name=data.get("name"))
    db.add(hq)
    db.commit()

    return {"message": "HQ created"}


@router.put("/update/{hq_id}")
def update_hq(hq_id: int, data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "super_admin":
        raise HTTPException(403, "Only super admin allowed")

    hq = db.get(HeadQuarter, hq_id)
    if not hq:
        raise HTTPException(404, "HQ not found")

    name = data.get("name")
    if not name:
        raise HTTPException(400, "HQ name is required")

    hq.name = name
    db.commit()

    return {"message": "HQ updated"}


@router.delete("/delete/{hq_id}")
def delete_hq(hq_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "super_admin":
        raise HTTPException(403, "Only super admin allowed")

    hq = db.get(HeadQuarter, hq_id)
    if not hq:
        raise HTTPException(404, "HQ not found")

    has_units = db.query(Unit).filter(Unit.hq_id == hq_id).first()
    if has_units:
        raise HTTPException(400, "Cannot delete HQ while units are linked")

    db.delete(hq)
    db.commit()

    return {"message": "HQ deleted"}
