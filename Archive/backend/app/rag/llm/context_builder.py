from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult

# ---------------------------------------------------------------------------
# Token / character budget
# ---------------------------------------------------------------------------
# llama3 8B context window ≈ 8 192 tokens ≈ ~32 000 chars
# Reserve: system prompt (~1 500) + query (~300) + answer (~2 000) = ~3 800
# Available for context: ~28 000 chars  →  use 6 000 to be safe with Ollama
MAX_CONTEXT_CHARS = 6_000

# How many chars to show per prose chunk (truncate long ones)
MAX_PROSE_CHARS = 500

# How many chars to show per command description
MAX_DESC_CHARS = 300


def build_context(results: List["SearchResult"], query: str) -> str:
    """
    Convert top-K SearchResult objects into a single formatted context
    string that the LLM receives.

    Two formats are produced depending on result type:

    ListItem (command result)
    -------------------------
    [Source 1 | commands.pdf | File Commands | Command #2 | file_commands]
    Command     : ls -al
    Description : Formatted listing with hidden files

    Prose chunk
    -----------
    [Source 2 | doctrine.pdf | Page 7 | Introduction to Operations]
    <content text …>

    Sources are included in relevance order (best first) until the
    character budget is exhausted.

    Args:
        results : Reranked SearchResult list (already in score order)
        query   : Original user query (used only for debug logging)

    Returns:
        Multi-block context string separated by "---" dividers.
    """
    if not results:
        return ""

    blocks: List[str] = []
    total_chars = 0

    for i, r in enumerate(results, start=1):
        if total_chars >= MAX_CONTEXT_CHARS:
            break

        block = _format_result(i, r)
        blocks.append(block)
        total_chars += len(block)

    context = "\n---\n".join(blocks)
    print(f"[CONTEXT] Built context: {len(blocks)} sources, {total_chars} chars")
    return context


def get_source_summary(results: List["SearchResult"]) -> List[dict]:
    """
    Return a deduplicated list of source metadata dicts for the API response.

    Each dict is suitable for rendering a citation in the frontend:
      { file_name, page_number, section, branch, doc_type, score, title }

    Sources are deduplicated by (file_name, page_number) — prose chunks
    from the same page are collapsed into one citation entry.
    """
    seen: set[tuple] = set()
    sources: List[dict] = []

    for r in results:
        key = (r.file_name, r.page_number, r.section)
        if key in seen:
            continue
        seen.add(key)

        sources.append({
            "file_name":   r.file_name,
            "page_number": r.page_number,
            "section":     r.section,
            "branch":      r.branch,
            "doc_type":    r.doc_type,
            "year":        r.year,
            "score":       round(r.score, 3),
            "title":       r.get_display_title(),
            # Command-specific extras (None for prose results)
            "command":     r.command if r.is_list_item else None,
            "rank":        r.rank_in_section if r.is_list_item else None,
            "category":    r.category if r.is_list_item else None,
            "is_command":  r.is_list_item,
        })

    return sources


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_result(index: int, r: "SearchResult") -> str:
    """Format a single SearchResult as a labelled context block."""
    if r.is_list_item and r.command:
        return _format_list_item(index, r)
    return _format_prose(index, r)


def _format_list_item(index: int, r: "SearchResult") -> str:
    rank_str    = f"Command #{r.rank_in_section}" if r.rank_in_section else "Command"
    category    = r.category or "unknown"
    description = (r.description or r.content or "")[:MAX_DESC_CHARS]

    return (
        f"[Source {index} | {r.file_name} | {r.section} | {rank_str} | {category}]\n"
        f"Command     : {r.command}\n"
        f"Description : {description}"
    )


def _format_prose(index: int, r: "SearchResult") -> str:
    heading   = f" | {r.heading}" if r.heading else ""
    content   = r.content[:MAX_PROSE_CHARS]
    if len(r.content) > MAX_PROSE_CHARS:
        content += "…"

    return (
        f"[Source {index} | {r.file_name} | Page {r.page_number}{heading} | {r.section}]\n"
        f"{content}"
    )