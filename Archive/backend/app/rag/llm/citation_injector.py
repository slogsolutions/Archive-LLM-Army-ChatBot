from __future__ import annotations
"""
Citation Injector — Stage 9b of the pipeline.

The LLM is prompted to reference sources as [Source 1], [Source 2] etc.
This module replaces those placeholders with real, human-readable citations
that include the actual file name, page number, and section.

Before injection:
  "The ls command lists files [Source 1]. Use ls -al for hidden files [Source 2]."

After injection:
  "The ls command lists files [commands.pdf, p.1, File Commands].
   Use ls -al for hidden files [commands.pdf, p.1, File Commands]."

If the LLM did not insert [Source N] markers (it sometimes won't),
a "References" block is appended at the end instead.
"""

import re
from typing import List


# Matches [Source 1], [Source 2], [source 3] (case-insensitive)
_SOURCE_REF_RE = re.compile(r"\[source\s*(\d+)\]", re.IGNORECASE)


def inject_citations(answer: str, sources: List[dict]) -> str:
    """
    Replace [Source N] placeholders in `answer` with real citation text.

    Args:
        answer  : Raw LLM answer (may contain [Source N] markers)
        sources : Output of context_builder.get_source_summary()
                  Each dict has: file_name, page_number, section, is_command,
                  command, rank, score, title

    Returns:
        Answer with citations replaced/appended.
    """
    if not answer:
        return answer

    if not sources:
        return answer

    # Track which source indices are actually referenced in the answer
    referenced_indices: set[int] = set()

    def _replace(m: re.Match) -> str:
        idx = int(m.group(1))                # 1-based
        referenced_indices.add(idx)
        source = _get_source(sources, idx)   # None if out of range
        if source is None:
            return m.group(0)                # Keep original if index invalid
        return _format_inline(source)

    replaced = _SOURCE_REF_RE.sub(_replace, answer)

    # If no [Source N] markers were found in the answer, append a references block
    if not referenced_indices:
        replaced = replaced + "\n\n" + _build_references_block(sources)

    return replaced


def _get_source(sources: List[dict], idx: int) -> dict | None:
    """Return source at 1-based index, or None if out of range."""
    if 1 <= idx <= len(sources):
        return sources[idx - 1]
    return None


def _format_inline(source: dict) -> str:
    """
    Format a single source as an inline citation.

    Command result:  [commands.pdf · Command #2 · File Commands]
    Prose result:    [doctrine.pdf · p.7 · Introduction]
    """
    fname   = source.get("file_name", "unknown")
    page    = source.get("page_number", 0)
    section = source.get("section", "")

    if source.get("is_command") and source.get("command"):
        rank    = source.get("rank", "")
        rank_str = f"Command #{rank} · " if rank else ""
        return f"[{fname} · {rank_str}{section}]"
    else:
        page_str = f"p.{page} · " if page else ""
        return f"[{fname} · {page_str}{section}]"


def _build_references_block(sources: List[dict]) -> str:
    """
    Build a numbered references section to append when no inline
    [Source N] markers were used by the LLM.
    """
    lines = ["**References:**"]
    for i, s in enumerate(sources, start=1):
        lines.append(f"{i}. {_format_inline(s)}  (relevance: {s.get('score', 0):.2f})")
    return "\n".join(lines)