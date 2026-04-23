def build_rbac_filter(user):
    clauses = []

    if not user:
        return clauses

    # 🔥 Rank visibility
    clauses.append({
        "range": {
            "min_visible_rank": {
                "gte": user.rank_level
            }
        }
    })

    role = user.role

    # SUPER ADMIN → no restriction
    if role == "super_admin":
        return clauses

    # HQ ADMIN
    if role == "hq_admin":
        clauses.append({"term": {"hq_id": user.hq_id}})

    # UNIT ADMIN
    elif role == "unit_admin":
        clauses.append({"term": {"unit_id": user.unit_id}})

    # OFFICER / CLERK
    elif role in ["officer", "clerk"]:
        clauses.append({"term": {"unit_id": user.unit_id}})

    # TRAINEE
    elif role == "trainee":
        clauses.append({"term": {"uploaded_by": user.id}})

    return clauses