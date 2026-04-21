from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.branch import Branch
from app.models.unit import Unit
from app.core.deps import get_current_user, get_db
from app.core.audit import audit_action

router = APIRouter()


def _branch_dict(branch, units) -> dict:
    unit = next((u for u in units if u.id == branch.unit_id), None)
    return {
        "id": branch.id,
        "name": branch.name,
        "description": branch.description,
        "unit_id": branch.unit_id,
        "unit_name": unit.name if unit else None,
        "hq_id": unit.hq_id if unit else None,
    }


@router.get("/")
@audit_action("GET_HQ")
def list_branches(user=Depends(get_current_user), db: Session = Depends(get_db)):
    all_units = db.query(Unit).all()
    query = db.query(Branch)

    if user.role == "super_admin":
        branches = query.order_by(Branch.name).all()
    elif user.role == "hq_admin":
        unit_ids = [u.id for u in all_units if u.hq_id == user.hq_id]
        branches = query.filter(Branch.unit_id.in_(unit_ids)).order_by(Branch.name).all()
    elif user.role == "unit_admin":
        branches = query.filter(Branch.unit_id == user.unit_id).order_by(Branch.name).all()
    elif user.branch_id:
        branch = db.get(Branch, user.branch_id)
        branches = [branch] if branch else []
    else:
        branches = []

    return [_branch_dict(b, all_units) for b in branches]


@router.post("/create")
@audit_action("CREATE_HQ")
def create_branch(data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):

    if user.role not in ["super_admin", "hq_admin", "unit_admin"]:
        raise HTTPException(403, "Not allowed")

    unit_id = data.get("unit_id")
    if not unit_id:
        raise HTTPException(400, "Unit is required")

    name = data.get("name")
    if not name:
        raise HTTPException(400, "Branch name is required")
    name = name.strip().upper()

    # Unit Admin restriction
    if user.role == "unit_admin" and user.unit_id != unit_id:
        raise HTTPException(403, "Wrong unit")

    existing = db.query(Branch).filter(
        Branch.unit_id == unit_id,
        Branch.name.ilike(name)
    ).first()
    if existing:
        raise HTTPException(400, "This branch already exists in this unit")

    branch = Branch(
        name=name,
        description=data.get("description"),
        unit_id=unit_id
    )

    db.add(branch)
    db.commit()
    db.refresh(branch)

    return {"message": f"Branch '{branch.name}' created", "id": branch.id, "name": branch.name}


@router.put("/update/{branch_id}")
@audit_action("UPDATE_HQ")
def update_branch(branch_id: int, data: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Branch not found")

    if user.role not in ["super_admin", "hq_admin", "unit_admin"]:
        raise HTTPException(403, "Not allowed")

    unit = db.get(Unit, branch.unit_id)
    if user.role == "hq_admin" and (not unit or unit.hq_id != user.hq_id):
        raise HTTPException(403, "Wrong HQ")

    if user.role == "unit_admin" and user.unit_id != branch.unit_id:
        raise HTTPException(403, "Wrong unit")

    name = data.get("name")
    if not name:
        raise HTTPException(400, "Branch name is required")
    name = name.strip().upper()

    unit_id = data.get("unit_id", branch.unit_id)
    if user.role == "unit_admin" and user.unit_id != unit_id:
        raise HTTPException(403, "Wrong unit")

    existing = db.query(Branch).filter(
        Branch.id != branch_id,
        Branch.unit_id == unit_id,
        Branch.name.ilike(name)
    ).first()
    if existing:
        raise HTTPException(400, "This branch already exists in this unit")

    branch.name = name
    branch.description = data.get("description")
    branch.unit_id = unit_id
    db.commit()

    return {"message": "Branch updated"}


@router.delete("/delete/{branch_id}")
@audit_action("DELETE_HQ")
def delete_branch(branch_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    branch = db.get(Branch, branch_id)
    if not branch:
        raise HTTPException(404, "Branch not found")

    if user.role not in ["super_admin", "hq_admin", "unit_admin"]:
        raise HTTPException(403, "Not allowed")

    unit = db.get(Unit, branch.unit_id)
    if user.role == "hq_admin" and (not unit or unit.hq_id != user.hq_id):
        raise HTTPException(403, "Wrong HQ")

    if user.role == "unit_admin" and user.unit_id != branch.unit_id:
        raise HTTPException(403, "Wrong unit")

    db.delete(branch)
    db.commit()

    return {"message": "Branch deleted"}
