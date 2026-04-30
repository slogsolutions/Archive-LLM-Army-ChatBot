from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult

# ---------------------------------------------------------------------------
# Character budgets
# ---------------------------------------------------------------------------
# llama3 8B context ≈ 8 192 tokens ≈ 32 000 chars.
# Keep context tight on CPU — larger context = much slower first token.
# 3 500 chars ≈ ~875 tokens, leaves plenty of headroom for prompt + answer.
MAX_CONTEXT_CHARS = 3_500

# Truncate each prose chunk to keep diversity across sources.
MAX_PROSE_CHARS = 800

# Command description budget (list items are shorter by nature)
MAX_DESC_CHARS = 400


def build_context(results: List["SearchResult"], query: str = "") -> str:  # noqa: ARG001
    """
    Convert top-K SearchResult objects into a single formatted context string.

    Two layouts are produced:

    Majority list-item results (> 60 % are ListItems)
    --------------------------------------------------
    Shows all items as a numbered list in rank order so the LLM can
    enumerate them completely.

    Prose / mixed results
    ---------------------
    Shows each chunk as a labelled block with full content (up to
    MAX_PROSE_CHARS) in relevance order until the char budget runs out.
    """
    if not results:
        return ""

    list_count = sum(1 for r in results if r.is_list_item)
    if list_count >= max(1, len(results) * 0.6):
        return _format_list_context(results)

    return _format_prose_context(results)


def build_parent_child_context(results: List["SearchResult"], _query: str = "") -> str:
    """
    Same as build_context — parent-child aware formatting is handled at
    index time (children already have heading prepended). Falls through to
    the standard formatters.
    """
    return build_context(results, _query)


def get_source_summary(results: List["SearchResult"]) -> List[dict]:
    """
    Return a deduplicated list of source metadata dicts for the API response.
    Sources are deduplicated by (file_name, page_number, section).
    """
    seen: set[tuple] = set()
    sources: List[dict] = []

    for r in results:
        key = (r.file_name, r.page_number, r.section)
        if key in seen:
            continue
        seen.add(key)

        sources.append({
            "doc_id":      r.doc_id,
            "file_name":   r.file_name,
            "page_number": r.page_number,
            "section":     r.section,
            "branch":      r.branch,
            "doc_type":    r.doc_type,
            "year":        r.year,
            "score":       round(r.score, 3),
            "title":       r.get_display_title(),
            "command":     r.command if r.is_list_item else None,
            "rank":        r.rank_in_section if r.is_list_item else None,
            "category":    r.category if r.is_list_item else None,
            "is_command":  r.is_list_item,
        })

    return sources


# ---------------------------------------------------------------------------
# Internal formatters
# ---------------------------------------------------------------------------

def _format_list_context(results: List["SearchResult"]) -> str:
    """
    Format list items as a clean numbered list for the LLM.

    Items are sorted by (section, rank_in_section) so the LLM receives
    them in the intended document order — critical for accurate enumeration.
    """
    # Sort: group by section, then by rank within each section
    sorted_results = sorted(
        results,
        key=lambda r: (r.section or "", r.rank_in_section or 999, r.chunk_index),
    )

    # Build one block per section
    sections: dict[str, List["SearchResult"]] = {}
    for r in sorted_results:
        key = r.section or r.file_name or "Document"
        sections.setdefault(key, []).append(r)

    blocks: List[str] = []
    total_chars = 0

    for section_name, items in sections.items():
        fname = items[0].file_name if items else ""
        header = f"[Section: {section_name} | {fname}]\n"
        lines  = [header]

        for r in items:
            if total_chars >= MAX_CONTEXT_CHARS:
                break

            if r.is_list_item and r.command:
                desc = (r.description or r.content or "")[:MAX_DESC_CHARS]
                rank = r.rank_in_section or "•"
                line = f"{rank}. {r.command} — {desc}"
            else:
                line = f"• {r.content[:MAX_PROSE_CHARS]}"

            lines.append(line)
            total_chars += len(line)

        blocks.append("\n".join(lines))

    context = "\n\n".join(blocks)
    print(f"[CONTEXT] Built list context: {len(sorted_results)} items, {total_chars} chars")
    print("─" * 60)
    print(context[:2000] + ("…" if len(context) > 2000 else ""))
    print("─" * 60)
    return context


def _format_prose_context(results: List["SearchResult"]) -> str:
    """
    Format prose chunks as labelled source blocks in relevance order.
    Each block includes the FULL chunk content (up to MAX_PROSE_CHARS)
    so the LLM never misses information buried in the second half of a chunk.
    """
    blocks: List[str] = []
    total_chars = 0

    for i, r in enumerate(results, start=1):
        if total_chars >= MAX_CONTEXT_CHARS:
            break

        block = _format_result(i, r)
        blocks.append(block)
        total_chars += len(block)

    context = "\n---\n".join(blocks)
    print(f"[CONTEXT] Built prose context: {len(blocks)} sources, {total_chars} chars")
    print("─" * 60)
    for j, b in enumerate(blocks, 1):
        print(f"[CONTEXT chunk {j}]\n{b}\n")
    print("─" * 60)
    return context


def _format_result(index: int, r: "SearchResult") -> str:
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
    heading = f" | {r.heading}" if r.heading else ""
    content = r.content[:MAX_PROSE_CHARS]
    if len(r.content) > MAX_PROSE_CHARS:
        content += "…"

    return (
        f"[Source {index} | {r.file_name} | Page {r.page_number}{heading} | {r.section}]\n"
        f"{content}"
    )


# ---------------------------------------------------------------------------
# Parent-child context builder
# ---------------------------------------------------------------------------

# Per-parent section char budget.  1 200 chars ≈ 300 tokens — a full H2
# section comfortably fits.  The LLM gets complete section text instead of
# a fragmented child chunk, dramatically reducing hallucination.
MAX_SECTION_CHARS = 1_200


def build_parent_child_context(
    results: "List[SearchResult]",
    query: str = "",    # noqa: ARG001 — reserved for future query-highlighting
) -> str:
    """
    Build LLM context using full parent sections.

    For results with a populated _parent_doc (new parent-child index format):
      → Use the full section text (up to MAX_SECTION_CHARS)
      → Label with [Source N | file | p.X–Y | Heading]

    For results WITHOUT _parent_doc (old flat index format):
      → Fall back to build_context() prose format

    This lets the two ingestion formats co-exist without any breaking changes.
    The LLM always receives complete, well-structured sections regardless of
    which format the document was indexed with.
    """
    # Separate results by format
    has_parent  = [r for r in results if r._parent_doc]
    flat_only   = [r for r in results if not r._parent_doc]

    blocks: List[str] = []
    total_chars = 0
    source_idx  = 1

    # ── Parent-child results → full section text ──────────────────────────
    # Deduplicate by parent_id (multiple children may point to same parent)
    seen_pids: set[str] = set()
    ordered: "List[SearchResult]" = []
    for r in sorted(has_parent, key=lambda x: -x.score):
        pid = r.parent_id or ""
        if pid not in seen_pids:
            seen_pids.add(pid)
            ordered.append(r)

    for r in ordered:
        if total_chars >= MAX_CONTEXT_CHARS:
            break
        p = r._parent_doc
        if not p:
            continue

        section_text = (p.get("full_section_text") or r.content or "")[:MAX_SECTION_CHARS]
        heading      = p.get("heading") or r.heading or ""
        file_nm      = p.get("file_name") or r.file_name
        p_start      = p.get("page_range_start") or r.page_number
        p_end        = p.get("page_range_end")   or p_start
        page_ref     = f"p.{p_start}–{p_end}" if p_end != p_start else f"p.{p_start}"

        block = (
            f"[Source {source_idx} | {file_nm} | {page_ref} | {heading}]\n"
            f"{section_text}"
        )
        blocks.append(block)
        total_chars += len(block)
        source_idx  += 1

    # ── Flat results → existing prose format ─────────────────────────────
    if flat_only and total_chars < MAX_CONTEXT_CHARS:
        # Re-use the existing prose formatter; renumber sources from source_idx
        flat_blocks: List[str] = []
        for i, r in enumerate(flat_only, start=source_idx):
            if total_chars >= MAX_CONTEXT_CHARS:
                break
            block = _format_result(i, r)
            flat_blocks.append(block)
            total_chars += len(block)
        if flat_blocks:
            blocks.append("\n---\n".join(flat_blocks))

    context = "\n\n---\n\n".join(blocks)
    n_parents = source_idx - 1
    print(f"[CONTEXT] parent-child: {n_parents} sections + {len(flat_only)} flat, {total_chars} chars")
    return context
