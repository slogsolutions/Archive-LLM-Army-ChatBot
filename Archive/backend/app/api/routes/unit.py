from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.unit import Unit
from app.models.branch import Branch
from app.core.deps import get_current_user, get_db

router = APIRouter()


@router.get("/")
def list_units(user=Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Unit)

    if user.role == "super_admin":
        return query.order_by(Unit.name).all()

    if user.role == "hq_admin":
        return query.filter(Unit.hq_id == user.hq_id).order_by(Unit.name).all()

    if user.unit_id:
        unit = db.get(Unit, user.unit_id)
        return [unit] if unit else []

    return []


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


@router.put("/update/{unit_id}")
def update_unit(unit_id: int, data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")

    if user.role not in ["super_admin", "hq_admin"]:
        raise HTTPException(403, "Not allowed")

    if user.role == "hq_admin" and user.hq_id != unit.hq_id:
        raise HTTPException(403, "Wrong HQ")

    name = data.get("name")
    hq_id = data.get("hq_id", unit.hq_id)

    if not name:
        raise HTTPException(400, "Unit name is required")

    if user.role == "hq_admin" and user.hq_id != hq_id:
        raise HTTPException(403, "Wrong HQ")

    unit.name = name
    unit.hq_id = hq_id
    db.commit()

    return {"message": "Unit updated"}


@router.delete("/delete/{unit_id}")
def delete_unit(unit_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")

    if user.role not in ["super_admin", "hq_admin"]:
        raise HTTPException(403, "Not allowed")

    if user.role == "hq_admin" and user.hq_id != unit.hq_id:
        raise HTTPException(403, "Wrong HQ")

    has_branches = db.query(Branch).filter(Branch.unit_id == unit_id).first()
    if has_branches:
        raise HTTPException(400, "Cannot delete unit while branches are linked")

    db.delete(unit)
    db.commit()

    return {"message": "Unit deleted"}
