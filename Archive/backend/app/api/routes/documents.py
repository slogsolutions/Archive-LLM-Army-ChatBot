from fastapi import APIRouter, UploadFile, File, Depends, HTTPException , Form
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import uuid


from app.core.deps import get_current_user, get_db
from app.models.document import Document
from app.services.minio_service import upload_file, get_file_stream
from app.core.rbac import get_filter
# from app.services.search_service import search_documents
from app.workers.ocr_tasks import process_document

# ✅ RBAC Dependency
from app.core.document_access import require_document_access

router = APIRouter()


# =========================
# UPLOAD DOCUMENT
# =========================
@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),

    # ✅ MAKE THESE MANDATORY
    branch: str = Form(...),
    document_type: str = Form(...),

    # Optional (keep if needed)
    hq_id: int = None,
    unit_id: int = None,
    branch_id: int = None,
    min_visible_rank: int | None = None,

    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    # 🔒 ONLY CLERK + OFFICER
    if user.role not in ["officer", "clerk"]:
        raise HTTPException(403, "Only clerk or officer can upload")

    if not file:
        raise HTTPException(400, "File required")

    # ✅ VALIDATE REQUIRED FIELDS
    if not branch or not document_type:
        raise HTTPException(400, "Branch and Document Type are required")

    # Normalize IDs (optional)
    hq_id = int(hq_id) if hq_id is not None else user.hq_id
    unit_id = int(unit_id) if unit_id is not None else user.unit_id
    branch_id = int(branch_id) if branch_id is not None else user.branch_id

    # Scope validation (keep your logic)
    if user.hq_id and hq_id and user.hq_id != hq_id:
        raise HTTPException(403, "Wrong HQ")

    if user.unit_id and unit_id and user.unit_id != unit_id:
        raise HTTPException(403, "Wrong Unit")

    if user.role == "clerk" and user.clerk_type not in ["junior", "senior"]:
        raise HTTPException(400, "Invalid clerk setup")

    # Unique filename
    unique_filename = f"{uuid.uuid4()}_{file.filename}"

    # file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    # ✅ Upload to MinIO with structured path
    file_path = upload_file(file, unique_filename, branch, document_type)

    # Approval logic
    is_approved = False
    approved_by = None

    if user.role == "officer":
        is_approved = True
        approved_by = user.id
    elif user.role == "clerk" and user.clerk_type == "senior":
        is_approved = True
        approved_by = user.id

    # ✅ SAVE METADATA
    doc = Document(
        file_name=unique_filename,
        minio_path=file_path,
        file_size=file_size,
        file_type=file.content_type,

        # ✅ NEW METADATA
        branch_name=branch,
        document_type_name=document_type,

        hq_id=hq_id,
        unit_id=unit_id,
        branch_id=branch_id,

        uploaded_by=user.id,
        is_approved=is_approved,
        approved_by=approved_by,
        min_visible_rank=min_visible_rank if min_visible_rank is not None else 6,
        status="uploaded"
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Background OCR
    try:
        process_document.delay(doc.id)
    except Exception:
        # Keep upload usable in local development even when the worker/broker is down.
        pass

    return {
        "doc_id": doc.id,
        "file_name": unique_filename,
        "path": file_path,
        "approved": is_approved
    }


# =========================
# SEARCH
# =========================
@router.get("/search")
def search(query: str, user=Depends(get_current_user)):
    return search_documents(query)




# =========================
# APPROVE DOCUMENT
# =========================
@router.post("/approve/{doc_id}")
def approve_document(
    doc=Depends(require_document_access("approve")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if doc.is_approved:
        return {"message": "Already approved"}

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
    doc=Depends(require_document_access("view"))
):
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

    for key, value in filters.items():
        if value is not None:
            query = query.filter(getattr(Document, key) == value)

    # hide unapproved for trainee
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        query = query.filter(Document.is_approved == True)

    return query.all()


# =========================
# UPDATE OCR TEXT
# =========================
@router.put("/update-text/{doc_id}")
def update_text(
    text: str,
    doc=Depends(require_document_access("view")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if user.role not in ["clerk", "officer"]:
        raise HTTPException(403, "Only clerk/officer can edit")

    doc.corrected_text = text
    doc.status = "reviewed"

    db.commit()

    return {"message": "Updated"}


# =========================
# DOWNLOAD DOCUMENT
# =========================

# @router.get("/download/{doc_id}")
# def download_document(
#     doc=Depends(require_document_access("view"))
# ):

#     file_stream = get_file_stream(doc.minio_path)

#     return StreamingResponse(
#         file_stream,
#         media_type=doc.file_type or "application/octet-stream",
#         headers={
#             "Content-Disposition": f'attachment; filename="{doc.file_name}"'
#         }
#     )


# # =========================
# # SEARCH
# # =========================
# @router.get("/search")
# def search(query: str, user=Depends(get_current_user)):
#     return search_documents(query)