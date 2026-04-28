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
You are a military document assistant for the Indian Army.
Answer ONLY from the CONTEXT DOCUMENTS provided. Be concise and direct.
If the answer is not in the context, say: "Not found in the provided documents."
Never invent facts. Cite sources as [Source N].
"""

_FORMAT_HINTS: dict[str, str] = {
    "command": (
        "If the context has a CLI command entry: show Command, Description, [Source N]. "
        "If prose, answer in 2-4 plain factual sentences."
    ),
    "list": (
        "List ALL items as: N. name — description [Source N]. "
        "Do not skip items. End with 'Total: N items.'"
    ),
    "prose": (
        "Answer in 2-5 clear sentences. Cite every claim with [Source N]."
    ),
    "mixed": (
        "Give the direct answer in 1-2 sentences, then supporting detail. Cite [Source N]."
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
        return f"QUESTION: {query}\n\nNo documents found. State the information is unavailable."

    return (
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {query}\n"
        f"Answer concisely from the context only."
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
