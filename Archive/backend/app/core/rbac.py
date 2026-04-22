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

    if not user or not document:
        return False

    # 🔥 DELETE / APPROVE (HANDLE FIRST)
    if action == "delete":
        if user.role in ["officer", "unit_admin", "hq_admin", "super_admin"]:
            return True

        if user.role == "clerk":
            if user.clerk_type == "senior":
                return True
            if user.clerk_type == "junior":
                return user.id == document.uploaded_by

        return False

    if action == "approve":
        return user.role in ["officer", "unit_admin", "hq_admin", "super_admin"]

    # =========================
    # 🔥 APPROVAL BLOCK
    # =========================
    if not document.is_approved and user.role not in [
        "officer", "unit_admin", "hq_admin", "super_admin"
    ]:
        return False

    # =========================
    # 🔥 VISIBILITY
    # =========================
    if user.rank_level > document.min_visible_rank:
        return False

    # SUPER ADMIN
    if user.role == "super_admin":
        return True

    # HQ ADMIN
    if user.role == "hq_admin":
        return user.hq_id == document.hq_id

    # UNIT ADMIN
    if user.role == "unit_admin":
        return user.unit_id == document.unit_id

    # OFFICER
    if user.role == "officer":
        return (
            user.unit_id == document.unit_id and
            user.branch_id == document.branch_id
        )

    # CLERK
    if user.role == "clerk":
        return (
            user.unit_id == document.unit_id and
            user.branch_id == document.branch_id and
            user.task_category == document.document_type_name
        )

    # TRAINEE
    if user.role == "trainee":
        return user.id == document.uploaded_by

    return False

# =========================
# 2. FILTER (Multiple Docs)
# =========================

def get_filter(user):

    if not user:
        return {"id": None}

    if user.role == "super_admin":
        return {}

    if user.role == "hq_admin":
        return {"hq_id": user.hq_id}

    if user.role == "unit_admin":
        return {"unit_id": user.unit_id}

    if user.role == "officer":
        return {
            "unit_id": user.unit_id,
            "branch_id": user.branch_id
        }

    if user.role == "clerk":
        return {
            "unit_id": user.unit_id,
            "branch_id": user.branch_id,
            "document_type_name": user.task_category
        }

    if user.role == "trainee":
        return {"uploaded_by": user.id}

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
