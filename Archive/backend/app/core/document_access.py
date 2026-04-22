from fastapi import Depends, HTTPException
from app.core.rbac import check_access
from app.core.deps import get_current_user, get_db
from app.models.document import Document


def require_document_access(action: str):
    def checker(doc_id: int, user=Depends(get_current_user), db=Depends(get_db)):
        doc = db.get(Document, doc_id)

        if not doc:
            raise HTTPException(404, "Document not found")

        if not check_access(user, doc, action):
            raise HTTPException(403, "Access denied")

        return doc

    return checker