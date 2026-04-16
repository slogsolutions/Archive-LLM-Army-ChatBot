"""
RBAC CORE

check_access → Single document (view, download, delete, approve)
get_filter   → Multiple documents (list, search)

NOTE:
This is NOT middleware.
This is a central RBAC policy layer used inside routes/services.
"""


# =========================
# 1. ACCESS CHECK (Single)
# =========================

def check_access(user, document, action: str = "view"):
    """
    user      → current logged-in user
    document  → DB object (must have hq_id, unit_id, branch_id, uploaded_by, task_category)
    action    → view | download | delete | approve
    """

    # Safety check
    if not user or not document:
        return False

    # 1. Super Admin → full access
    if user.role == "super_admin":
        return True

    # 2. HQ Admin
    if user.role == "hq_admin":
        return user.hq_id == document.hq_id

    # 3. Unit Admin
    if user.role == "unit_admin":
        return user.unit_id == document.unit_id

    # 4. Officer (Branch Head)
    if user.role == "officer":
        if action in ["delete", "approve"]:
            return True  # officer can approve/delete inside branch

        return (
            user.unit_id == document.unit_id and
            user.branch_id == document.branch_id
        )

    # 5. Clerk
    if user.role == "clerk":
        # Restrict sensitive actions
        if action in ["delete", "approve"]:
            return False

        return (
            user.unit_id == document.unit_id and
            user.branch_id == document.branch_id and
            user.task_category == document.task_category
        )

    # 6. Trainee
    if user.role == "trainee":
        # Only own documents
        if action in ["delete", "approve"]:
            return False

        return user.id == document.uploaded_by

    return False


# =========================
# 2. FILTER (Multiple Docs)
# =========================

def get_filter(user):
    """
    Returns dict for SQLAlchemy filter_by(**filters)

    Used in:
    - List documents
    - Search APIs
    """

    if not user:
        return {"id": None}  # return nothing

    # Super Admin → no restriction
    if user.role == "super_admin":
        return {}

    # HQ Admin
    if user.role == "hq_admin":
        return {"hq_id": user.hq_id}

    # Unit Admin
    if user.role == "unit_admin":
        return {"unit_id": user.unit_id}

    # Officer
    if user.role == "officer":
        return {
            "unit_id": user.unit_id,
            "branch_id": user.branch_id
        }

    # Clerk
    if user.role == "clerk":
        return {
            "unit_id": user.unit_id,
            "branch_id": user.branch_id,
            "task_category": user.task_category
        }

    # Trainee
    if user.role == "trainee":
        return {"uploaded_by": user.id}

    # Default → no access
    return {"id": None}


# =========================
# 3. USAGE EXAMPLES
# =========================

"""
# Example 1: View Document

from app.core.rbac import check_access

doc = db.query(Document).get(doc_id)

if not check_access(current_user, doc, "view"):
    raise HTTPException(status_code=403, detail="Access denied")

return doc
"""


"""
# Example 2: Delete Document

if not check_access(current_user, doc, "delete"):
    raise HTTPException(status_code=403, detail="Not allowed to delete")

db.delete(doc)
db.commit()
"""


"""
# Example 3: List Documents

from app.core.rbac import get_filter

filters = get_filter(current_user)

docs = db.query(Document).filter_by(**filters).all()
"""