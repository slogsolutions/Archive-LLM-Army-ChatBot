from __future__ import annotations
import re

_YEAR_RE    = re.compile(r"\b(19|20)\d{2}\b")
_BRANCH_RE  = re.compile(r"\bbranch\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)
_TYPE_RE    = re.compile(r"\btype\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)",   re.IGNORECASE)
_SECTION_RE = re.compile(r"\bsection\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)


def parse_query(raw: str) -> dict:
    """
    Normalise a user query and extract embedded filter hints.

    Recognises patterns such as:
      "training manual 2023"           → year=2023
      "branch alpha operations report" → branch="alpha"
      "type: SOP section: logistics"   → doc_type="SOP", section="logistics"

    Returns:
        {
          "query":   clean query string (filter hints stripped),
          "filters": {year, branch, doc_type, section}  (only non-None values)
        }
    """
    query = raw.strip()
    filters: dict = {}

    year_m = _YEAR_RE.search(query)
    if year_m:
        filters["year"] = int(year_m.group())

    branch_m = _BRANCH_RE.search(query)
    if branch_m:
        filters["branch"] = branch_m.group(1).strip()

    type_m = _TYPE_RE.search(query)
    if type_m:
        filters["doc_type"] = type_m.group(1).strip()

    section_m = _SECTION_RE.search(query)
    if section_m:
        filters["section"] = section_m.group(1).strip()

    # Strip recognised filter phrases from the query so BM25 is cleaner
    clean = _BRANCH_RE.sub("", query)
    clean = _TYPE_RE.sub("", clean)
    clean = _SECTION_RE.sub("", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    return {"query": clean or query, "filters": filters}
