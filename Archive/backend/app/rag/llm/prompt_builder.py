from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult


# ---------------------------------------------------------------------------
# Branch-specific domain context injected into the system prompt.
# Keys are lowercase partial branch names — matched by substring.
# ---------------------------------------------------------------------------
_BRANCH_NOTES: dict[str, str] = {
    "infantry":    "Focus on ground tactics, weapon handling, section/platoon drills, and field procedures.",
    "signals":     "Focus on communication protocols, radio frequencies, cipher procedures, and signal SOPs.",
    "medical":     "Focus on CASEVAC, field medicine, triage categories, and medical evacuation procedures.",
    "engineer":    "Focus on construction, demolition, obstacle breaching, mine clearing, and bridging.",
    "artillery":   "Focus on fire missions, gun drills, ballistics, target acquisition, and ammunition.",
    "armoured":    "Focus on armoured vehicle operations, tank tactics, and crew drills.",
    "aviation":    "Focus on aviation operations, helicopter SOPs, and air-ground coordination.",
    "logistics":   "Focus on supply chain, ammunition management, rations, and equipment maintenance.",
    "intelligence": "Focus on intelligence gathering, analysis, and reporting formats.",
    "it":          "Focus on IT systems, commands, network procedures, and technical documentation.",
    "linux":       "Focus on Linux commands, system administration, and terminal procedures.",
}

_DEFAULT_BRANCH_NOTE = (
    "Provide precise military doctrine, procedure, or technical information "
    "as documented in the source material."
)

# ---------------------------------------------------------------------------
# Core system prompt — rules the LLM must follow for army RAG
# ---------------------------------------------------------------------------
_SYSTEM_BASE = """\
You are a precise military document assistant for the Indian Army.

RULES (non-negotiable):
1. Answer ONLY from the provided context documents. Never use outside knowledge.
2. If the answer is not in the context, say exactly:
   "This information is not available in the provided documents."
3. For numbered lists or commands, always include the rank/number in your answer.
4. Cite every claim: [Source: <filename>, page <N>, section <section>].
   If multiple sources support a claim, cite all of them.
5. Be concise and structured. Use bullet points for lists, numbered steps for procedures.
6. Never speculate, estimate, or fill gaps with assumptions.
7. If a query asks for a specific command number (e.g. "command #5"), return that
   exact entry — rank, command, and full description.
8. Maintain military precision: use correct terminology from the source material.
"""


# ---------------------------------------------------------------------------
# Intent-specific answer format guidance
# ---------------------------------------------------------------------------
_FORMAT_HINTS: dict[str, str] = {
    "command": (
        "FORMAT: Lead with the command name and rank. "
        "Follow with the full description. "
        "End with the source citation."
    ),
    "list": (
        "FORMAT: Present results as a numbered list in rank order. "
        "Each item: <rank>. <command> — <description> [Source: …]"
    ),
    "prose": (
        "FORMAT: Write a clear, structured paragraph. "
        "Use section headings if explaining multiple sub-topics. "
        "Cite sources inline."
    ),
    "mixed": (
        "FORMAT: Lead with the most direct answer. "
        "Add supporting detail below. Cite sources."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_system_prompt(
    results: List["SearchResult"] | None = None,
    intent: str = "mixed",
) -> str:
    """
    Build the LLM system prompt.

    Optionally enriched with:
    - Dominant branch context (detected from retrieved results)
    - Intent-specific formatting guidance

    Args:
        results : Reranked SearchResult list (used for branch detection)
        intent  : Query intent from detect_query_intent()

    Returns:
        Complete system prompt string.
    """
    branch_note   = _detect_branch_note(results)
    format_hint   = _FORMAT_HINTS.get(intent, _FORMAT_HINTS["mixed"])

    return (
        f"{_SYSTEM_BASE}\n"
        f"DOMAIN CONTEXT: {branch_note}\n\n"
        f"{format_hint}"
    )


def build_user_prompt(query: str, context: str) -> str:
    """
    Build the user-turn prompt with context injected.

    The context is placed BEFORE the question so the LLM reads the
    evidence first, then the question — this reduces hallucination.

    Args:
        query   : Cleaned user query string
        context : Output of context_builder.build_context()

    Returns:
        Complete user prompt string.
    """
    if not context:
        return (
            f"QUESTION: {query}\n\n"
            "No relevant documents were found. "
            "Please state that the information is not available."
        )

    return (
        f"CONTEXT DOCUMENTS:\n"
        f"{context}\n\n"
        f"---\n\n"
        f"QUESTION: {query}\n\n"
        f"Answer based strictly on the context documents above. "
        f"Do not use any outside knowledge:"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_branch_note(results: List["SearchResult"] | None) -> str:
    """
    Infer the dominant branch from the retrieved results and return
    a domain-specific context note for the system prompt.

    Falls back to the default note if results are absent or ambiguous.
    """
    if not results:
        return _DEFAULT_BRANCH_NOTE

    # Count occurrences of each branch value
    branch_counts: dict[str, int] = {}
    for r in results:
        b = (r.branch or "").lower().strip()
        if b:
            branch_counts[b] = branch_counts.get(b, 0) + 1

    if not branch_counts:
        return _DEFAULT_BRANCH_NOTE

    dominant = max(branch_counts, key=branch_counts.get)

    # Match dominant branch against known keys (substring match)
    for key, note in _BRANCH_NOTES.items():
        if key in dominant:
            return note

    return _DEFAULT_BRANCH_NOTE