from __future__ import annotations
import uuid

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.document import Document
from app.services.minio_service import upload_file, get_file_stream
from app.core.rbac import get_filter
from app.core.document_access import require_document_access
from app.workers.ocr_tasks import process_document

from app.services.minio_service import move_to_deleted

router = APIRouter()


# =========================
# UPLOAD DOCUMENT
# =========================
@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    branch: str = Form(...),
    document_type: str = Form(...),
    hq_id: int = None,
    unit_id: int = None,
    branch_id: int = None,
    section: str = Form(None),
    year: int = Form(None),
    min_visible_rank: int | None = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ["officer", "clerk"]:
        raise HTTPException(403, "Only clerk or officer can upload")

    if not file:
        raise HTTPException(400, "File required")

    if not branch or not document_type:
        raise HTTPException(400, "Branch and Document Type are required")

    hq_id = int(hq_id) if hq_id is not None else user.hq_id
    unit_id = int(unit_id) if unit_id is not None else user.unit_id
    branch_id = int(branch_id) if branch_id is not None else user.branch_id

    if user.hq_id and hq_id and user.hq_id != hq_id:
        raise HTTPException(403, "Wrong HQ")
    if user.unit_id and unit_id and user.unit_id != unit_id:
        raise HTTPException(403, "Wrong Unit")
    if user.role == "clerk" and user.clerk_type not in ["junior", "senior"]:
        raise HTTPException(400, "Invalid clerk setup")

    unique_filename = f"{uuid.uuid4()}_{file.filename}"

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    file_path = upload_file(file, unique_filename, branch, document_type)

    is_approved = False
    approved_by = None
    if user.role == "officer":
        is_approved = True
        approved_by = user.id
    elif user.role == "clerk" and user.clerk_type == "senior":
        is_approved = True
        approved_by = user.id

    doc = Document(
        file_name=unique_filename,
        minio_path=file_path,
        file_size=file_size,
        file_type=file.content_type,
        branch_name=branch,
        document_type_name=document_type,
        section=section,
        year=year,
        hq_id=hq_id,
        unit_id=unit_id,
        branch_id=branch_id,
        uploaded_by=user.id,
        is_approved=is_approved,
        approved_by=approved_by,
        min_visible_rank=min_visible_rank if min_visible_rank is not None else 6,
        status="uploaded",
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        process_document.delay(doc.id)
    except Exception:
        pass

    return {
        "doc_id": doc.id,
        "file_name": unique_filename,
        "path": file_path,
        "approved": is_approved,
    }


# =========================
# SEARCH (hybrid BM25 + KNN)
# =========================
@router.get("/search")
def search_documents(
    query: str = Query(..., min_length=1),
    branch: str = Query(None),
    doc_type: str = Query(None),
    year: int = Query(None),
    section: str = Query(None),
    top_k: int = Query(10, ge=1, le=50),
    user=Depends(get_current_user),
):
    """
    Hybrid semantic + keyword search over all indexed document chunks.
    Results are scoped to the authenticated user's RBAC context.
    """
    from app.rag.retriever.retriever import search

    filters: dict = {}
    if branch:
        filters["branch"] = branch
    if doc_type:
        filters["doc_type"] = doc_type
    if year:
        filters["year"] = year
    if section:
        filters["section"] = section

    results = search(query=query, filters=filters, top_k=top_k, user=user)

    return [
        {
            "doc_id":       r.doc_id,
            "content":      r.content,
            "score":        r.score,
            "page_number":  r.page_number,
            "chunk_index":  r.chunk_index,
            "heading":      r.heading,
            "file_name":    r.file_name,
            "branch":       r.branch,
            "doc_type":     r.doc_type,
            "year":         r.year,
            "section":      r.section,
        }
        for r in results
    ]


# =========================
# APPROVE DOCUMENT
# =========================
@router.post("/approve/{doc_id}")
def approve_document(
    doc=Depends(require_document_access("approve")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
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
    doc=Depends(require_document_access("view")),
):
    if doc.is_deleted:
        raise HTTPException(404, "Document not found")

    return doc


# =========================
# LIST DOCUMENTS
# =========================
@router.get("/")
def list_documents(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = get_filter(user)
    query = db.query(Document)

    for key, value in filters.items():
        if value is not None:
            query = query.filter(getattr(Document, key) == value)

    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        query = query.filter(Document.is_approved == True)

    query = query.filter(Document.is_deleted == False)
    return query.all()


# =========================
# UPDATE OCR TEXT
# =========================
@router.put("/update-text/{doc_id}")
def update_text(
    text: str,
    doc=Depends(require_document_access("view")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
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
@router.get("/download/{doc_id}")
def download_document(
    doc=Depends(require_document_access("view")),
):
    if doc.is_deleted:
        raise HTTPException(404, "Document not found")

    file_stream = get_file_stream(doc.minio_path)

    return StreamingResponse(
        file_stream,
        media_type=doc.file_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.file_name}"'
        },
    )


# =========================
# RE-INDEX DOCUMENT
# =========================
@router.post("/reindex/{doc_id}")
def reindex_document(
    doc=Depends(require_document_access("view")),
    user=Depends(get_current_user),
):
    """Trigger re-ingestion of a document that was already OCR'd."""
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        raise HTTPException(403, "Insufficient permissions")

    if not (doc.corrected_text or doc.ocr_text):
        raise HTTPException(400, "Document has no OCR text to re-index")

    try:
        process_document.delay(doc.id)
    except Exception as e:
        raise HTTPException(500, f"Could not queue reindex: {e}")

    return {"message": "Re-index queued", "doc_id": doc.id}


# =========================
# DELETE
# =========================
@router.delete("/delete/{doc_id}")
def delete_document(
    doc=Depends(require_document_access("view")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Officer or Senior Clerk → direct delete
    if user.role == "officer" or (
        user.role == "clerk" and user.clerk_type == "senior"
    ):
        # 🔥 MOVE FILE IN MINIO
        new_path = move_to_deleted(doc.minio_path)

        doc.minio_path = new_path
        doc.is_deleted = True
        doc.deleted_by = user.id
        doc.status = "deleted"

        db.commit()

        return {"message": "Document deleted (moved to deleted folder)"}

    # Junior Clerk → request delete
    if user.role == "clerk" and user.clerk_type == "junior":
        doc.delete_requested = True
        doc.delete_requested_by = user.id
        doc.status = "delete_requested"

        db.commit()

        return {"message": "Delete request sent"}

    raise HTTPException(403, "Not allowed")



# =========================
# DELETE APRROVAL
# =========================

@router.post("/approve-delete/{doc_id}")
def approve_delete(
    doc=Depends(require_document_access("approve")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not doc.delete_requested:
        raise HTTPException(400, "No delete request found")

    if user.role not in ["officer"] and not (
        user.role == "clerk" and user.clerk_type == "senior"
    ):
        raise HTTPException(403, "Not allowed")

    # 🔥 MOVE FILE IN MINIO
    new_path = move_to_deleted(doc.minio_path)

    doc.minio_path = new_path
    doc.is_deleted = True
    doc.deleted_by = user.id
    doc.status = "deleted"

    db.commit()

    return {"message": "Delete approved & file moved"}