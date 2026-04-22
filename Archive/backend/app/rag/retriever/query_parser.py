from __future__ import annotations
import re

_YEAR_RE    = re.compile(r"\b(19|20)\d{2}\b")
_BRANCH_RE  = re.compile(r"\bbranch\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)
_TYPE_RE    = re.compile(r"\btype\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)
_SECTION_RE = re.compile(r"\bsection\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)


def parse_query(raw: str) -> dict:
    """
    Extract filters from query and clean it
    """

    query = raw.strip()
    filters: dict = {}

    # 🔹 YEAR
    year_m = _YEAR_RE.search(query)
    if year_m:
        filters["year"] = int(year_m.group())

    # 🔹 BRANCH
    branch_m = _BRANCH_RE.search(query)
    if branch_m:
        filters["branch"] = branch_m.group(1).strip().lower()

    # 🔹 TYPE
    type_m = _TYPE_RE.search(query)
    if type_m:
        filters["doc_type"] = type_m.group(1).strip().lower()

    # 🔹 SECTION
    section_m = _SECTION_RE.search(query)
    if section_m:
        filters["section"] = section_m.group(1).strip().lower()

    # 🔹 CLEAN QUERY (remove filter keywords)
    clean = _BRANCH_RE.sub("", query)
    clean = _TYPE_RE.sub("", clean)
    clean = _SECTION_RE.sub("", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    return {
        "query": clean or query,
        "filters": filters
    }