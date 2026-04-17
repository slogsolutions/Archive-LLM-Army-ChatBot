from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import uuid

from app.core.deps import get_current_user, get_db
from app.models.document import Document
from app.services.minio_service import upload_file, get_file_stream
from app.core.rbac import check_access, get_filter
from app.services.search_service import search_documents
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

    if not file:
        raise HTTPException(400, "File required")

    # 🔒 Scope validation
    if user.hq_id and user.hq_id != hq_id:
        raise HTTPException(403, "Wrong HQ")

    if user.unit_id and user.unit_id != unit_id:
        raise HTTPException(403, "Wrong Unit")

    if user.branch_id and user.branch_id != branch_id:
        raise HTTPException(403, "Wrong Branch")

    # 🔒 Clerk safety
    if user.role == "clerk" and user.clerk_type not in ["junior", "senior"]:
        raise HTTPException(400, "Invalid clerk setup")

    unique_filename = f"{uuid.uuid4()}_{file.filename}"

    # get file size safely
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    file_path = upload_file(file, unique_filename)

    # =========================
    # APPROVAL LOGIC
    # =========================
    is_approved = False
    approved_by = None

    if user.role == "officer":
        is_approved = True
        approved_by = user.id

    elif user.role == "clerk" and user.clerk_type == "senior":
        is_approved = True
        approved_by = user.id

    # =========================
    # SAVE
    # =========================
    doc = Document(
        file_name=unique_filename,
        minio_path=file_path,
        file_size=file_size,
        file_type=file.content_type,
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
    db.refresh(doc)

    # 🔥 OCR async
    process_document.delay(doc.id)

    return {
        "doc_id": doc.id,
        "file_name": unique_filename,
        "approved": is_approved
    }


# =========================
# APPROVE DOCUMENT
# =========================

@router.post("/approve/{doc_id}")
def approve_document(
    doc_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    doc = db.get(Document, doc_id)

    if not doc:
        raise HTTPException(404)

    if doc.is_approved:
        return {"message": "Already approved"}

    if not check_access(user, doc, "approve"):
        raise HTTPException(403)

    doc.is_approved = True
    doc.approved_by = user.id
    doc.status = "approved"

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
    query = db.query(Document)

    # 🔥 FIX: safe filtering
    for key, value in filters.items():
        if value is not None:
            query = query.filter(getattr(Document, key) == value)

    # 🔥 hide unapproved for low roles
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        query = query.filter(Document.is_approved == True)

    return query.all()


# =========================
# UPDATE OCR TEXT
# =========================

@router.put("/update-text/{doc_id}")
def update_text(
    doc_id: int,
    text: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    doc = db.get(Document, doc_id)

    if not doc:
        raise HTTPException(404)

    if not check_access(user, doc, "view"):
        raise HTTPException(403)

    if user.role not in ["clerk", "officer"]:
        raise HTTPException(403)

    doc.corrected_text = text
    doc.status = "reviewed"

    db.commit()

    return {"message": "Updated"}


# =========================
# SEARCH API 
# =========================

@router.get("/search")
def search(
    query: str,
    user=Depends(get_current_user)   #  SECURITY FIX
):
    return search_documents(query)


# =========================
# DOWNLOAD DOCUMENT
# =========================

@router.get("/download/{doc_id}")
def download_document(
    doc_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    doc = db.get(Document, doc_id)

    if not doc:
        raise HTTPException(404, "Document not found")

    if not check_access(user, doc, "view"):
        raise HTTPException(403, "Access denied")

    file_stream = get_file_stream(doc.minio_path)

    return StreamingResponse(
        file_stream,
        media_type=doc.file_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.file_name}"'
        }
    )