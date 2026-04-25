from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_YEAR_RE     = re.compile(r"\b(19|20)\d{2}\b")
_BRANCH_RE   = re.compile(r"\bbranch\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)
_TYPE_RE     = re.compile(r"\btype\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)
_SECTION_RE  = re.compile(r"\bsection\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)

# Rank: "command 5", "command #5", "#5", "rank 5"
_RANK_RE     = re.compile(
    r"\b(?:command\s*#?|rank\s*#?)(\d+)\b",
    re.IGNORECASE
)

# Category: only when explicitly written as a known category keyword
# NOTE: we do NOT strip these from the clean query — they help BM25
_CATEGORY_RE = re.compile(
    r"\b(file[_\s]commands?|process[_\s]management|process[_\s]mgmt|"
    r"network\s+commands?|compression|searching|permissions|shortcuts|"
    r"system[_\s]info)\b",
    re.IGNORECASE,
)

# Category normalisation map
_CATEGORY_MAP = {
    "file command":        "file_commands",
    "file commands":       "file_commands",
    "file_commands":       "file_commands",
    "file_command":        "file_commands",
    "process management":  "process_management",
    "process mgmt":        "process_management",
    "process_management":  "process_management",
    "network command":     "network",
    "network commands":    "network",
    "compression":         "compression",
    "searching":           "searching",
    "permissions":         "permissions",
    "shortcuts":           "shortcuts",
    "system info":         "system_info",
    "system_info":         "system_info",
}

# Exact command pattern: "command ls -al", "what is ls -al"
_COMMAND_RE  = re.compile(r"\bcommand\s+['\"]?([a-z][\w\-\.]*)['\"]?", re.IGNORECASE)


def parse_query(raw: str) -> dict:
    """
    Extract structured filters from natural language query.

    IMPORTANT: The clean query keeps all meaningful content words.
    Only explicit metadata keywords (branch:, type:, section:, year:)
    and rank numbers are stripped. Category words like "file commands"
    and "network" are kept in the clean query because they help BM25.

    Returns
    -------
    {
        "query":   str,   # cleaned query for BM25 + embedding
        "filters": dict,  # structured ES filter hints (all soft boosts)
    }

    Examples
    --------
    "show all file commands"
        → query="show all file commands", filters={category: "file_commands"}

    "find command 5 in file commands"
        → query="find file commands", filters={rank_in_section: 5, category: "file_commands"}

    "enrolment procedure" + external filters={doc_type: "regulation"}
        → query="enrolment procedure", filters={}  (external filters merged by retriever)

    "branch: signals type: manual documents 2023"
        → query="documents", filters={branch:"signals", doc_type:"manual", year:2023}
    """
    query   = raw.strip()
    filters: dict = {}

    # ── Year ──────────────────────────────────────────────────────────────
    year_m = _YEAR_RE.search(query)
    if year_m:
        filters["year"] = int(year_m.group())
        # Only strip year from query if it was part of a metadata phrase
        # (bare years like "2023 documents" — keep, "year: 2023" — strip)
        if re.search(r"\byear\s*[:\-]\s*\d{4}", query, re.IGNORECASE):
            query = re.sub(r"\byear\s*[:\-]\s*\d{4}", "", query)

    # ── Branch (only when explicit "branch: xxx" syntax) ──────────────────
    branch_m = _BRANCH_RE.search(query)
    if branch_m:
        filters["branch"] = branch_m.group(1).strip().lower()
        query = _BRANCH_RE.sub("", query)

    # ── Doc type (only when explicit "type: xxx" syntax) ──────────────────
    type_m = _TYPE_RE.search(query)
    if type_m:
        filters["doc_type"] = type_m.group(1).strip().lower()
        query = _TYPE_RE.sub("", query)

    # ── Section (only when explicit "section: xxx" syntax) ────────────────
    section_m = _SECTION_RE.search(query)
    if section_m:
        filters["section"] = section_m.group(1).strip().lower()
        query = _SECTION_RE.sub("", query)

    # ── Rank in section ───────────────────────────────────────────────────
    # Strip rank number from query (it's meaningless for BM25/KNN)
    rank_m = _RANK_RE.search(query)
    if rank_m:
        filters["rank_in_section"] = int(rank_m.group(1))
        query = _RANK_RE.sub("", query)

    # ── Category — extract as filter but KEEP in query for BM25 ──────────
    category_m = _CATEGORY_RE.search(raw)   # search on original raw
    if category_m:
        cat_raw = category_m.group(1).lower().replace("_", " ").strip()
        # Normalise to underscore form
        filters["category"] = _CATEGORY_MAP.get(cat_raw, cat_raw.replace(" ", "_"))
        # Do NOT remove from query — "file commands" helps BM25 find the right doc

    # ── Exact command filter ───────────────────────────────────────────────
    command_m = _COMMAND_RE.search(raw)
    if command_m:
        filters["command"] = command_m.group(1).lower()

    # ── Clean up query whitespace ──────────────────────────────────────────
    query = re.sub(r"\s+", " ", query).strip()

    # Fallback: if cleaning made query empty or too short, use the raw query
    if len(query.split()) < 2:
        query = raw.strip()

    return {
        "query":   query,
        "filters": filters,
    }


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

def detect_query_intent(query: str) -> str:
    """
    Classify query intent for reranker boosting.

    Returns: "command" | "list" | "prose" | "mixed"
    """
    q = query.lower()

    has_command = any(x in q for x in [
        "command", "show me", "find", "get",
        "rank", "position", "which is", "#",
        "ls", "cd", "pwd", "mkdir", "grep", "chmod",
        "ping", "ssh", "ps", "kill", "top",
    ])
    has_list = any(x in q for x in [
        "all", "list", "show all", "every", "each", "all the",
    ])
    has_prose = any(x in q for x in [
        "explain", "describe", "tell me about", "background",
        "overview", "detail", "information about", "procedure",
        "what is the", "how does", "what is", "what are",
        "how to", "define", "definition", "meaning of",
    ])

    if has_prose and not has_command:
        return "prose"
    if has_list:
        return "list"
    if has_command:
        return "command"
    return "mixed"