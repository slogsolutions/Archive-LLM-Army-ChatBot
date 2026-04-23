
# IMPROVED VERSION


from __future__ import annotations
import re

# Existing patterns
_YEAR_RE    = re.compile(r"\b(19|20)\d{2}\b")
_BRANCH_RE  = re.compile(r"\bbranch\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)
_TYPE_RE    = re.compile(r"\btype\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)
_SECTION_RE = re.compile(r"\bsection\s*[:\-]?\s*([a-zA-Z0-9 ]+?)(?=\s+\w+:|$)", re.IGNORECASE)

# 🔥 NEW patterns for command-aware queries
_RANK_RE     = re.compile(r"\b(?:command\s+)?#?(\d+)(?:\s+in\s+\w+)?|rank\s*[:\-]?\s*(\d+)", re.IGNORECASE)
_CATEGORY_RE = re.compile(
    r"\b(file_commands|file\s+commands|process_management|process\s+mgmt|"
    r"network|compression|searching|permissions|shortcuts|system_info)\b",
    re.IGNORECASE
)
_COMMAND_RE  = re.compile(r"\bcommand\s+['\"]?([a-z\-\.]+)['\"]?", re.IGNORECASE)


def parse_query(raw: str) -> dict:
    """
    Extract filters from natural language query and clean it.
    
    🔥 NEW: Now supports command-specific queries.
    
    Examples:
        "find command 5 in File Commands"
        → {query: "find", filters: {rank_in_section: 5, section: "file commands"}}
        
        "show me all network commands"
        → {query: "show me all", filters: {category: "network"}}
        
        "what is ls -al"
        → {query: "what is", filters: {command: "ls -al"}}
        
        "command #2 process management"
        → {query: "", filters: {rank_in_section: 2, category: "process_management"}}
    """

    query = raw.strip()
    filters: dict = {}

    # ========== EXISTING FILTERS ==========
    
    # 🔹 YEAR
    year_m = _YEAR_RE.search(query)
    if year_m:
        filters["year"] = int(year_m.group())

    # 🔹 BRANCH
    branch_m = _BRANCH_RE.search(query)
    if branch_m:
        filters["branch"] = branch_m.group(1).strip().lower()

    # 🔹 TYPE (doc type)
    type_m = _TYPE_RE.search(query)
    if type_m:
        filters["doc_type"] = type_m.group(1).strip().lower()

    # 🔹 SECTION (document section like "File Commands")
    section_m = _SECTION_RE.search(query)
    if section_m:
        filters["section"] = section_m.group(1).strip().lower()

    # ========== NEW FILTERS (Command-aware) ==========
    
    # 🔹 RANK IN SECTION (position in list: 1, 2, 3...)
    rank_m = _RANK_RE.search(query)
    if rank_m:
        rank_str = rank_m.group(1) or rank_m.group(2)
        if rank_str:
            filters["rank_in_section"] = int(rank_str)

    # 🔹 CATEGORY (type of command: file_commands, network, etc.)
    category_m = _CATEGORY_RE.search(query)
    if category_m:
        category = category_m.group(1).lower().replace(" ", "_")
        filters["category"] = category

    # 🔹 COMMAND (exact command like "ls -al")
    command_m = _COMMAND_RE.search(query)
    if command_m:
        filters["command"] = command_m.group(1).lower()

    # ========== CLEAN QUERY (remove all filter keywords) ==========
    clean = query
    clean = _YEAR_RE.sub("", clean)
    clean = _BRANCH_RE.sub("", clean)
    clean = _TYPE_RE.sub("", clean)
    clean = _SECTION_RE.sub("", clean)
    clean = _RANK_RE.sub("", clean)
    clean = _CATEGORY_RE.sub("", clean)
    clean = _COMMAND_RE.sub("", clean)
    
    # Normalize spacing
    clean = re.sub(r"\s+", " ", clean).strip()

    return {
        "query": clean or raw,
        "filters": filters
    }


# ============================================================================
# INTENT DETECTION (for reranker hints)
# ============================================================================

def detect_query_intent(query: str) -> str:
    """
    Detect if user is looking for:
    - "command": specific command info (rank, description)
    - "prose": general documentation
    - "list": listing commands
    - "mixed": both
    
    Used by reranker to boost relevant result types.
    """
    query_lower = query.lower()
    
    # Command-specific intent
    has_command_words = any(x in query_lower for x in [
        "command", "what is", "show me", "find", "get", "list", 
        "rank", "position", "which is", "how", "#"
    ])
    
    # Prose intent
    has_prose_words = any(x in query_lower for x in [
        "explain", "describe", "tell me about", "background", 
        "overview", "detail", "information about"
    ])
    
    # List intent
    has_list_words = any(x in query_lower for x in [
        "all", "list", "show all", "every", "each", "all the"
    ])
    
    if has_command_words:
        return "command"
    elif has_list_words:
        return "list"
    elif has_prose_words:
        return "prose"
    else:
        return "mixed"


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test cases
    tests = [
        ("find command 5 in File Commands", 
         {"query": "find", "filters": {"rank_in_section": 5, "section": "file commands"}}),
        
        ("show me all network commands", 
         {"filters": {"category": "network"}}),
        
        ("what is command ls -al",
         {"filters": {"command": "ls -al"}}),
        
        ("list all process management commands",
         {"filters": {"category": "process_management"}}),
        
        ("command #2",
         {"filters": {"rank_in_section": 2}}),
        
        ("type: Linux command section: File Commands year: 2026",
         {"filters": {"doc_type": "linux command", "section": "file commands", "year": 2026}}),
    ]
    
    for raw, expected_partial in tests:
        result = parse_query(raw)
        print(f"Input: {raw}")
        print(f"Output: {result}")
        print()