from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult

_BRANCH_NOTES: dict[str, str] = {
    "infantry":    "Focus on ground tactics, weapon handling, section/platoon drills, and field procedures.",
    "signals":     "Focus on communication protocols, radio frequencies, cipher procedures, and signal SOPs.",
    "medical":     "Focus on CASEVAC, field medicine, triage categories, and medical evacuation procedures.",
    "engineer":    "Focus on construction, demolition, obstacle breaching, mine clearing, and bridging.",
    "artillery":   "Focus on fire missions, gun drills, ballistics, target acquisition, and ammunition.",
    "armoured":    "Focus on armoured vehicle operations, tank tactics, and crew drills.",
    "aviation":    "Focus on aviation operations, helicopter SOPs, and air-ground coordination.",
    "logistics":   "Focus on supply chain, ammunition management, rations, and equipment maintenance.",
    "intelligence":"Focus on intelligence gathering, analysis, and reporting formats.",
    "it":          "Focus on IT systems, commands, network procedures, and technical documentation.",
    "linux":       "Focus on Linux commands, system administration, and terminal procedures.",
}

_DEFAULT_BRANCH_NOTE = (
    "Provide precise military doctrine, procedure, or technical information "
    "as documented in the source material."
)

_SYSTEM_BASE = """\
You are a precise military document assistant for the Indian Army.

RULES (non-negotiable):
1. Answer ONLY using information present in the CONTEXT DOCUMENTS below.
2. If the exact answer is not in the context, say:
   "This information is not available in the provided documents."
   Do NOT invent, estimate, or fill gaps from outside knowledge.
3. Cite every claim with [Source N] where N matches the source number in the context.
4. Never speculate. Never hallucinate. Military precision is mandatory.
"""

_FORMAT_HINTS: dict[str, str] = {
    "command": (
        "FORMAT: If the context contains a specific command or CLI entry, present it clearly:\n"
        "  Command: <name>\n"
        "  Description: <what it does>\n"
        "  [Source N]\n"
        "If the context is prose (not a command entry), answer in plain factual sentences."
    ),
    "list": (
        "FORMAT: Present ALL items from the context as a numbered list in the exact order they appear.\n"
        "Each line: <rank>. <name/command> — <description> [Source N]\n"
        "Do NOT skip any item. Do NOT add items not in the context.\n"
        "End with a count: 'Total: N items.'"
    ),
    "prose": (
        "FORMAT: Write a clear, factual paragraph. "
        "Use the heading from the source if relevant. "
        "Cite sources inline as [Source N]. "
        "Keep it concise — 3 to 6 sentences unless the topic demands more."
    ),
    "mixed": (
        "FORMAT: Lead with the most direct answer in 1-2 sentences. "
        "Add supporting detail below. Cite sources as [Source N]."
    ),
}


def build_system_prompt(
    results: List["SearchResult"] | None = None,
    intent: str = "mixed",
) -> str:
    branch_note = _detect_branch_note(results)
    format_hint = _FORMAT_HINTS.get(intent, _FORMAT_HINTS["mixed"])

    return (
        f"{_SYSTEM_BASE}\n"
        f"DOMAIN CONTEXT: {branch_note}\n\n"
        f"{format_hint}"
    )


def build_user_prompt(query: str, context: str) -> str:
    if not context:
        return (
            f"QUESTION: {query}\n\n"
            "No relevant documents were found. "
            "State that the information is not available."
        )

    return (
        f"CONTEXT DOCUMENTS:\n"
        f"{context}\n\n"
        f"---\n\n"
        f"QUESTION: {query}\n\n"
        f"Answer based strictly on the context documents above. "
        f"Do not use any outside knowledge."
    )


def _detect_branch_note(results: List["SearchResult"] | None) -> str:
    if not results:
        return _DEFAULT_BRANCH_NOTE

    branch_counts: dict[str, int] = {}
    for r in results:
        b = (r.branch or "").lower().strip()
        if b:
            branch_counts[b] = branch_counts.get(b, 0) + 1

    if not branch_counts:
        return _DEFAULT_BRANCH_NOTE

    dominant = max(branch_counts, key=branch_counts.get)
    for key, note in _BRANCH_NOTES.items():
        if key in dominant:
            return note

    return _DEFAULT_BRANCH_NOTE
