from __future__ import annotations
import uuid

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from sqlalchemy import or_

from app.core.deps import get_current_user, get_db
from app.models.document import Document
from app.models.user import User
from app.models.hq import HeadQuarter
from app.models.unit import Unit
from app.models.branch import Branch
from app.services.minio_service import upload_file, get_file_stream
from app.core.rbac import get_filter
from app.core.document_access import require_document_access
from app.workers.ocr_tasks import process_document, index_corrected_text

from app.services.minio_service import move_to_deleted
from app.rag.vector_store.elastic_store import delete_doc_chunks
from app.models.document_chunks import DocumentChunk

from app.core.audit import audit_action
from app.core.logger import logger

router = APIRouter()


def _base_dict(doc: Document, db: Session) -> dict:
    hq = db.get(HeadQuarter, doc.hq_id) if doc.hq_id else None
    unit = db.get(Unit, doc.unit_id) if doc.unit_id else None
    branch = db.get(Branch, doc.branch_id) if doc.branch_id else None
    uploader = db.get(User, doc.uploaded_by) if doc.uploaded_by else None
    approver = db.get(User, doc.approved_by) if doc.approved_by else None

    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "minio_path": doc.minio_path,
        "file_size": doc.file_size,
        "file_type": doc.file_type,
        "hq_id": doc.hq_id,
        "unit_id": doc.unit_id,
        "branch_id": doc.branch_id,
        "hq_name": hq.name if hq else None,
        "unit_name": unit.name if unit else None,
        "branch_name": doc.branch_name or (branch.name if branch else None),
        "document_type_name": doc.document_type_name,
        "section": doc.section,
        "year": doc.year,
        "uploaded_by": doc.uploaded_by,
        "uploader_name": uploader.name if uploader else None,
        "is_approved": doc.is_approved,
        "approved_by": doc.approved_by,
        "approver_name": approver.name if approver else None,
        "rejected_by": doc.rejected_by,
        "rejector_name": db.get(User, doc.rejected_by).name if doc.rejected_by else None,
        "rejection_reason": doc.rejection_reason,
        "status": doc.status,
        "min_visible_rank": doc.min_visible_rank,
        "keywords": doc.keywords,
        "delete_requested": doc.delete_requested,
        "is_deleted": doc.is_deleted,
        "version": doc.version,
        "parent_id": doc.parent_id,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


def _enrich_list(doc: Document, db: Session) -> dict:
    return _base_dict(doc, db)


def _enrich(doc: Document, db: Session) -> dict:
    base = _base_dict(doc, db)
    base["ocr_text"] = doc.ocr_text
    base["corrected_text"] = doc.corrected_text
    return base


# =========================
# UPLOAD DOCUMENT
# =========================
@audit_action("UPLOAD_DOCUMENT")
@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    branch: str = Form(...),
    document_type: str = Form(...),
    hq_id: int = Form(None),
    unit_id: int = Form(None),
    branch_id: int = Form(None),
    section: str = Form(None),
    year: int = Form(None),
    min_visible_rank: int = Form(6),
    keywords: str = Form(None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info("validating document")

    if user.role not in ["officer", "clerk"]:
        raise HTTPException(403, "Only clerk or officer can upload")

    if not file:
        raise HTTPException(400, "File required")

    if not branch or not document_type:
        raise HTTPException(400, "Branch and Document Type are required")

    hq_id = hq_id if hq_id is not None else user.hq_id
    unit_id = unit_id if unit_id is not None else user.unit_id
    branch_id = branch_id if branch_id is not None else user.branch_id

    if user.hq_id and hq_id and user.hq_id != hq_id:
        raise HTTPException(403, "Wrong HQ")
    if user.unit_id and unit_id and user.unit_id != unit_id:
        raise HTTPException(403, "Wrong Unit")
    if user.role == "clerk" and user.clerk_type not in ["junior", "senior"]:
        raise HTTPException(400, "Invalid clerk setup")

    unique_filename = f"{uuid.uuid4()}_{file.filename}"

    file.file.seek(0, 2)
    file_size = file.file.tell()

    if file_size > 20 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 20MB)")

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

    # VERSIONING
    existing = db.query(Document).filter(
        Document.file_name == file.filename,
        Document.is_deleted == False
    ).first()

    version = 1
    parent_id = None

    if existing:
        version = existing.version + 1
        parent_id = existing.id

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
        min_visible_rank=min_visible_rank,
        keywords=keywords or None,
        status="uploaded",
        version=version,
        parent_id=parent_id,
    )

    db.add(doc)
    db.commit()
    db.refresh(doc)

    if is_approved:
        try:
            process_document.delay(doc.id)
        except Exception:
            logger.error("Failed to queue OCR task for doc_id=%s", doc.id)

    return {
        "doc_id": doc.id,
        "file_name": unique_filename,
        "path": file_path,
        "approved": is_approved,
        "message": "Uploaded. Pending officer approval before processing." if not is_approved else "Uploaded and queued for OCR processing.",
    }


# =========================
# SEARCH (hybrid BM25 + KNN)
# =========================
@audit_action("SEARCH_DOCUMENT")
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
    """Hybrid semantic + keyword search over all indexed document chunks."""
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
# PENDING APPROVALS LIST
# =========================
@router.get("/pending-approvals")
def list_pending_approvals(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Documents awaiting officer approval (uploaded by junior clerks)."""
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        raise HTTPException(403, "Not allowed")

    query = db.query(Document).filter(
        Document.is_approved == False,
        Document.is_deleted == False,
    )

    if user.role == "officer":
        if user.unit_id:
            query = query.filter(Document.unit_id == user.unit_id)
    elif user.role == "hq_admin":
        if user.hq_id:
            query = query.filter(Document.hq_id == user.hq_id)
    elif user.role == "unit_admin":
        if user.unit_id:
            query = query.filter(Document.unit_id == user.unit_id)

    docs = query.order_by(Document.id.desc()).all()
    return [_enrich_list(d, db) for d in docs]


# =========================
# PENDING DELETE REQUESTS
# =========================
@router.get("/pending-deletions")
def list_pending_deletions(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Documents where junior clerk has requested deletion."""
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        raise HTTPException(403, "Not allowed")

    query = db.query(Document).filter(
        Document.delete_requested == True,
        Document.is_deleted == False,
    )

    if user.role == "officer":
        if user.unit_id:
            query = query.filter(Document.unit_id == user.unit_id)
    elif user.role == "hq_admin":
        if user.hq_id:
            query = query.filter(Document.hq_id == user.hq_id)
    elif user.role == "unit_admin":
        if user.unit_id:
            query = query.filter(Document.unit_id == user.unit_id)

    docs = query.order_by(Document.id.desc()).all()
    return [_enrich_list(d, db) for d in docs]


# =========================
# APPROVE DOCUMENT
# =========================
@audit_action("APPROVE_DOCUMENT_UPLOAD")
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

    try:
        process_document.delay(doc.id)
    except Exception:
        logger.error("Failed to queue OCR task after approval for doc_id=%s", doc.id)

    return {"message": "Approved and queued for OCR processing"}


# =========================
# REJECT DOCUMENT
# =========================
@audit_action("REJECT_DOCUMENT")
@router.post("/reject/{doc_id}")
def reject_document(
    reason: str = Query(..., min_length=1),
    doc=Depends(require_document_access("approve")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if doc.is_approved:
        raise HTTPException(400, "Document already approved")
    if doc.status == "rejected":
        raise HTTPException(400, "Document already rejected")

    doc.rejected_by = user.id
    doc.rejection_reason = reason
    doc.status = "rejected"
    db.commit()

    return {"message": "Document rejected"}


# =========================
# VIEW DOCUMENT
# =========================
@audit_action("VIEW_DOCUMENT")
@router.get("/{doc_id}")
def get_document(
    doc=Depends(require_document_access("view")),
    db: Session = Depends(get_db),
):
    if doc.is_deleted:
        raise HTTPException(404, "Document not found")

    return _enrich(doc, db)


# =========================
# LIST DOCUMENTS
# =========================
@audit_action("LIST_DOCUMENT")
@router.get("/")
def list_documents(
    branch_name: str = Query(None),
    doc_type: str = Query(None),
    status: str = Query(None),
    year: int = Query(None),
    my_uploads: bool = Query(False),
    uploader_role: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info("Listing documents")

    query = db.query(Document)

    if my_uploads:
        # Only the caller's own uploads, regardless of approval — no RBAC scope filter
        query = query.filter(Document.uploaded_by == user.id)
    elif uploader_role:
        # Officers/admins viewing all docs uploaded by a specific role (e.g. clerks)
        if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
            raise HTTPException(403, "Not allowed")
        scope = get_filter(user)
        for key, value in scope.items():
            if value is not None:
                query = query.filter(getattr(Document, key) == value)
        uploader_ids = [u.id for u in db.query(User.id).filter(User.role == uploader_role).all()]
        if uploader_ids:
            query = query.filter(Document.uploaded_by.in_(uploader_ids))
        else:
            query = query.filter(False)
    else:
        filters = get_filter(user)
        for key, value in filters.items():
            if value is not None:
                query = query.filter(getattr(Document, key) == value)

        if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
            # Clerks/trainees see approved docs OR their own pending/rejected uploads
            query = query.filter(
                or_(Document.is_approved == True, Document.uploaded_by == user.id)
            )

    query = query.filter(Document.is_deleted == False)

    if branch_name:
        query = query.filter(Document.branch_name.ilike(f"%{branch_name}%"))
    if doc_type:
        query = query.filter(Document.document_type_name.ilike(f"%{doc_type}%"))
    if status:
        if status == "pending":
            query = query.filter(Document.is_approved == False, Document.status != "rejected")
        elif status == "rejected":
            query = query.filter(Document.status == "rejected")
        elif status == "delete_requested":
            query = query.filter(Document.delete_requested == True)
        else:
            query = query.filter(Document.status == status)
    if year:
        query = query.filter(Document.year == year)

    docs = query.order_by(Document.id.desc()).offset(skip).limit(limit).all()
    return [_enrich_list(d, db) for d in docs]


# =========================
# UPDATE OCR TEXT
# =========================
@audit_action("UPDATE_OCR_TEXT")
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
# INDEX WITH CORRECTED TEXT
# Indexes saved corrected_text (or ocr_text fallback) into Elasticsearch
# WITHOUT re-running OCR. Use this after editing OCR output.
# =========================
@audit_action("INDEX_TEXT_DOCUMENT")
@router.post("/index-text/{doc_id}")
def index_text_document(
    doc=Depends(require_document_access("view")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ["officer", "clerk", "unit_admin", "hq_admin", "super_admin"]:
        raise HTTPException(403, "Insufficient permissions")

    if not doc.is_approved:
        raise HTTPException(400, "Document must be approved before indexing")

    raw_text = (doc.corrected_text or doc.ocr_text or "").strip()
    if not raw_text:
        raise HTTPException(400, "No text to index. Run OCR first.")

    doc.status = "processing"
    db.commit()

    try:
        index_corrected_text.delay(doc.id)
    except Exception as e:
        raise HTTPException(500, f"Could not queue indexing: {e}")

    return {"message": "Queued for indexing with corrected text", "doc_id": doc.id}


# =========================
# DOWNLOAD DOCUMENT
# =========================
@audit_action("DOWNLOAD_DOCUMENT")
@router.get("/download/{doc_id}")
def download_document(
    doc=Depends(require_document_access("view")),
):
    if doc.is_deleted:
        raise HTTPException(404, "Document not found")

    try:
        minio_resp = get_file_stream(doc.minio_path)
    except Exception as e:
        raise HTTPException(500, f"File not found in storage: {e}")

    # Stream the MinIO response in 64 KB chunks and close the connection cleanly.
    def _iter_minio():
        try:
            for chunk in minio_resp.stream(amt=65536):
                yield chunk
        finally:
            minio_resp.close()
            minio_resp.release_conn()

    safe_name = doc.file_name.replace('"', "")
    return StreamingResponse(
        _iter_minio(),
        media_type=doc.file_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Access-Control-Allow-Origin": "*",   # belt-and-suspenders for CORS on download
        },
    )


# =========================
# UPDATE DOCUMENT ACCESS LEVEL
# =========================
@audit_action("UPDATE_DOCUMENT_ACCESS")
@router.patch("/{doc_id}/access")
def update_document_access(
    doc_id: int,
    data: dict,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update min_visible_rank for a document.
    Only officers/admins who have scope over the document can change its access level.
    They cannot set a rank lower than their own (cannot grant access above their level).
    """
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        raise HTTPException(403, "Only officers and above can change access levels")

    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    # Scope check — must be in same scope as document
    if user.role == "officer" and (user.unit_id != doc.unit_id or user.branch_id != doc.branch_id):
        raise HTTPException(403, "Out of scope")
    if user.role == "unit_admin" and user.unit_id != doc.unit_id:
        raise HTTPException(403, "Out of scope")
    if user.role == "hq_admin" and user.hq_id != doc.hq_id:
        raise HTTPException(403, "Out of scope")

    new_rank = data.get("min_visible_rank")
    if new_rank is None or not isinstance(new_rank, int) or not (1 <= new_rank <= 6):
        raise HTTPException(400, "min_visible_rank must be an integer 1–6")

    # Cannot grant access higher than your own level
    if new_rank < user.rank_level:
        raise HTTPException(403, "Cannot set access level higher than your own rank")

    doc.min_visible_rank = new_rank
    db.commit()
    return {"message": "Access level updated", "min_visible_rank": new_rank}


# =========================
# RE-INDEX DOCUMENT (re-runs full OCR pipeline)
# =========================
@audit_action("RE-INDEX_DOCUMENT")
@router.post("/reindex/{doc_id}")
def reindex_document(
    doc=Depends(require_document_access("view")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ["officer", "unit_admin", "hq_admin", "super_admin"]:
        raise HTTPException(403, "Insufficient permissions")

    doc_obj = db.get(Document, doc.id)
    if not doc_obj:
        raise HTTPException(404, "Document not found")

    if not doc_obj.is_approved:
        doc_obj.is_approved = True
        doc_obj.approved_by = user.id

    doc_obj.status = "uploaded"
    db.commit()

    try:
        process_document.delay(doc_obj.id)
    except Exception as e:
        raise HTTPException(500, f"Could not queue: {e}")

    was_approved = doc_obj.approved_by == user.id and not doc.is_approved
    return {
        "message": "Approved and queued for OCR processing" if was_approved else "Re-queued for OCR processing",
        "doc_id": doc_obj.id,
    }


# =========================
# DELETE
# =========================
@audit_action("DELETE_DOCUMENT")
@router.delete("/delete/{doc_id}")
def delete_document(
    doc=Depends(require_document_access("delete")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Junior Clerk → request delete (checked before direct delete)
    if user.role == "clerk" and user.clerk_type == "junior":
        doc.delete_requested = True
        doc.delete_requested_by = user.id
        doc.status = "delete_requested"
        db.commit()
        return {"message": "Delete request submitted for officer approval"}

    # Officer / Senior Clerk / Admins → direct delete (RBAC already verified in require_document_access)
    delete_doc_chunks(doc.id)

    db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc.id
    ).delete()

    new_path = move_to_deleted(doc.minio_path)

    doc.minio_path = new_path
    doc.is_deleted = True
    doc.deleted_by = user.id
    doc.status = "deleted"

    db.commit()

    return {"message": "Document deleted (MinIO + ES + DB)"}


# =========================
# DELETE APPROVAL
# =========================
@audit_action("DELETE_APPROVAL")
@router.post("/approve-delete/{doc_id}")
def approve_delete(
    doc=Depends(require_document_access("approve")),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not doc.delete_requested:
        raise HTTPException(400, "No delete request found")

    delete_doc_chunks(doc.id)

    db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc.id
    ).delete()

    new_path = move_to_deleted(doc.minio_path)

    doc.minio_path = new_path
    doc.is_deleted = True
    doc.deleted_by = user.id
    doc.status = "deleted"

    db.commit()

    return {"message": "Delete approved (MinIO + ES + DB cleaned)"}


# =========================
# DEBUGGING ROUTES
# =========================
@router.get("/chunks/{doc_id}")
def get_chunks(
    doc=Depends(require_document_access("view")),
    db: Session = Depends(get_db),
):
    return db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc.id
    ).all()
