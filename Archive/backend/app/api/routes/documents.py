from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.document import Document
from app.services.minio_service import upload_file
from app.core.rbac import check_access, get_filter
import uuid
from app.workers.ocr_tasks import process_document

router = APIRouter()


# =========================
# UPLOAD DOCUMENT
# =========================
@router.post("/upload")




def upload_document(
    file: UploadFile = File(...),
    hq_id: int = None,
    unit_id: int = None,
    branch_id: int = None,
    document_type_id: int = None,
    min_visible_rank: int = 6,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # 🔒 Scope validation
    if user.hq_id and user.hq_id != hq_id:
        raise HTTPException(status_code=403, detail="Wrong HQ")

    if user.unit_id and user.unit_id != unit_id:
        raise HTTPException(status_code=403, detail="Wrong Unit")

    if user.branch_id and user.branch_id != branch_id:
        raise HTTPException(status_code=403, detail="Wrong Branch")

    # ❌ Extra safety
    if not file:
        raise HTTPException(status_code=400, detail="File is required")

    # ✅ generate unique filename (ONLY ONCE)
    unique_filename = f"{uuid.uuid4()}_{file.filename}"

    # ✅ IMPORTANT: reset file pointer (safe)
    file.file.seek(0,2)  # go to end
    file_size = file.file.tell()
    file.file.seek(0)     # reset

    file_type = file.content_type


    # ✅ upload using SAME filename
    file_path = upload_file(file, unique_filename)

    # =========================
    # 🔥 APPROVAL LOGIC
    # =========================
    is_approved = False
    approved_by = None

    if user.role == "officer":
        is_approved = True
        approved_by = user.id

    elif user.role == "clerk":
        if user.clerk_type == "senior":
            is_approved = True
            approved_by = user.id

    # =========================
    # 💾 SAVE TO DB
    # =========================
    doc = Document(
        file_name=unique_filename,
        minio_path=file_path,  # must match minio path
        file_size=file_size,
        file_type=file_type,
        hq_id=hq_id,
        unit_id=unit_id,
        branch_id=branch_id,
        document_type_id=document_type_id,
        uploaded_by=user.id,
        is_approved=is_approved,
        approved_by=approved_by,
        min_visible_rank=min_visible_rank,
        status="uploaded"
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)  # ✅ important to get ID
    process_document.delay(doc.id)


    return {

        "doc_id": doc.id,
        "file_name": unique_filename,
        "path": file_path,
        "approved": is_approved
    }





# =========================
# APPROVE DOCUMENT
# =========================

@router.post("/approve/{doc_id}")
def approve_document(doc_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):

    doc = db.get(Document, doc_id)

    if not doc:
        raise HTTPException(404)

    if doc.is_approved:
        return {"message": "Already approved"}  # ✅ FIX

    if not check_access(user, doc, "approve"):
        raise HTTPException(403)

    doc.is_approved = True
    doc.approved_by = user.id
    doc.status = "approved"  # ✅ add status

    db.commit()

    return {"message": "Approved"}

# =========================
# VIEW DOCUMENT
# =========================
@router.get("/{doc_id}")
def get_document(
    doc_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    doc = db.get(Document, doc_id)

    if not doc:
        raise HTTPException(404)

    if not check_access(user, doc, "view"):
        raise HTTPException(403)

    return doc


# =========================
# LIST DOCUMENTS
# =========================
@router.get("/")
def list_documents(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    filters = get_filter(user)

    query = db.query(Document).filter_by(**filters)

    # 🔥 FIX: hide unapproved docs
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        query = query.filter(Document.is_approved == True)

    docs = query.all()

    return docs


# =========================
# UPDATE OCR TEXT
# =========================


@router.put("/update-text/{doc_id}")
def update_text(doc_id: int, text: str, user=Depends(get_current_user), db: Session = Depends(get_db)):

    doc = db.get(Document, doc_id)

    if not doc:
        raise HTTPException(404)

    # 🔥 FIX: RBAC check
    if not check_access(user, doc, "view"):
        raise HTTPException(403)

    if user.role not in ["clerk", "officer"]:
        raise HTTPException(403)

    doc.corrected_text = text
    doc.status = "reviewed"

    db.commit()

    return {"message": "Updated"}