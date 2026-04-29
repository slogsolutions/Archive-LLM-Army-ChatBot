"""
Confidence Scoring — Military-grade answer reliability gate.

Every answer gets a composite 0.0–1.0 confidence score. Answers below
REJECT_THRESHOLD are blocked before reaching the user, with an explicit
"Insufficient evidence" message that includes the confidence value and
what signal failed — mandatory for military audit trails.

Signals (weighted):
  0.35  retrieval quality   (top ES score + source diversity)
  0.30  faithfulness        (lexical overlap: answer words in context)
  0.20  answer validity     (not a "not available" non-answer)
  0.15  source diversity    (multiple unique documents, not one duplicated)

Threshold:
  >= 0.55  PASS   — high confidence, answer returned as-is
  >= 0.35  WARN   — moderate, answer returned with ⚠️ confidence note
  <  0.35  REJECT — answer blocked, user sees explicit rejection message
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
PASS_THRESHOLD   = 0.55   # answer returned cleanly
WARN_THRESHOLD   = 0.35   # answer returned with warning
REJECT_THRESHOLD = 0.35   # below this → block entirely

# Negative patterns — answers that claim the document doesn't have info
_NOT_AVAILABLE_RE = re.compile(
    r"(not (available|found|mentioned|present|in|covered|documented)|"
    r"no (information|details|mention|data)|"
    r"cannot (find|provide|answer)|"
    r"this information is not|"
    r"i (don't|do not) (have|know)|"
    r"insufficient (evidence|information))",
    re.IGNORECASE,
)

# Words that are pure stopwords — don't count toward faithfulness
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "and", "or", "but", "if",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "it", "its", "this", "that", "these", "those", "not", "only",
    "according", "based", "provided", "documents", "context", "source",
}


@dataclass
class ConfidenceResult:
    score:           float
    level:           str           # "high" | "moderate" | "low"
    retrieval_score: float
    faithfulness:    float
    validity:        float
    diversity:       float
    rejected:        bool
    reason:          str           # human-readable reason for rejection / warning


def compute_confidence(
    results:     "List[SearchResult]",
    answer:      str,
    faithfulness: float = 1.0,
) -> ConfidenceResult:
    """
    Compute composite confidence for a RAG answer.

    Parameters
    ----------
    results      : ranked search results used to generate the answer
    answer       : LLM-generated answer string
    faithfulness : lexical faithfulness score (0–1) from FaithfulnessGuard

    Returns
    -------
    ConfidenceResult
    """
    if not results:
        return ConfidenceResult(
            score=0.0, level="low",
            retrieval_score=0.0, faithfulness=0.0,
            validity=0.0, diversity=0.0,
            rejected=True,
            reason="No documents retrieved.",
        )

    # ── Signal 1: retrieval quality ───────────────────────────────────────
    # ES hybrid scores can exceed 1.0 (BM25 + KNN sum). Normalise by a
    # typical max of 5.0 — empirically most scores fall in 0–5 range.
    top_score  = results[0].score
    norm_top   = min(top_score / 5.0, 1.0)
    # Prefer having at least 3 results
    count_sig  = min(len(results) / 3.0, 1.0)
    retrieval_score = 0.7 * norm_top + 0.3 * count_sig

    # ── Signal 2: faithfulness (passed in from lexical check) ─────────────
    faith_score = max(0.0, min(faithfulness, 1.0))

    # ── Signal 3: answer validity (not a non-answer) ──────────────────────
    is_not_available = bool(_NOT_AVAILABLE_RE.search(answer or ""))
    validity_score   = 0.0 if is_not_available else 1.0

    # ── Signal 4: source diversity ────────────────────────────────────────
    unique_docs = len(set(r.doc_id for r in results))
    diversity_score = min(unique_docs / 3.0, 1.0)

    # ── Composite ─────────────────────────────────────────────────────────
    score = round(
        0.35 * retrieval_score
        + 0.30 * faith_score
        + 0.20 * validity_score
        + 0.15 * diversity_score,
        3,
    )

    # ── Level + rejection decision ────────────────────────────────────────
    if score >= PASS_THRESHOLD:
        level    = "high"
        rejected = False
        reason   = ""
    elif score >= WARN_THRESHOLD:
        level    = "moderate"
        rejected = False
        reasons  = []
        if retrieval_score < 0.5:
            reasons.append("weak retrieval match")
        if faith_score < 0.4:
            reasons.append("low lexical overlap with sources")
        if is_not_available:
            reasons.append("answer claims information unavailable")
        reason = "; ".join(reasons) or "moderate confidence"
    else:
        level    = "low"
        rejected = True
        reasons  = []
        if retrieval_score < 0.3:
            reasons.append("very weak retrieval")
        if faith_score < 0.3:
            reasons.append("answer poorly grounded in sources")
        if is_not_available:
            reasons.append("LLM claims information not in documents")
        if unique_docs < 2:
            reasons.append("only one source document")
        reason = "; ".join(reasons) or "low confidence"

    return ConfidenceResult(
        score=score,
        level=level,
        retrieval_score=round(retrieval_score, 3),
        faithfulness=round(faith_score, 3),
        validity=round(validity_score, 3),
        diversity=round(diversity_score, 3),
        rejected=rejected,
        reason=reason,
    )


def build_rejection_message(cr: ConfidenceResult, query: str) -> str:
    """
    Standard rejection message for military audit compliance.
    Includes the query, confidence score, and reason — all traceable.
    """
    return (
        f"⛔ **Answer rejected** — confidence too low to meet military reliability standards.\n\n"
        f"**Query**: {query}\n"
        f"**Confidence**: {cr.score:.0%} (threshold: {REJECT_THRESHOLD:.0%})\n"
        f"**Reason**: {cr.reason}\n\n"
        "Recommended actions:\n"
        "• Ensure the relevant document is indexed (check Archive)\n"
        "• Re-phrase the query with more specific terms\n"
        "• Upload a document that contains this information\n"
    )


def build_warning_note(cr: ConfidenceResult) -> str:
    """Inline warning appended to moderate-confidence answers."""
    return (
        f"\n\n---\n"
        f"⚠️ **Confidence: {cr.score:.0%}** (moderate) — {cr.reason}. "
        f"Cross-check with source documents before acting on this information."
    )


def keyword_coverage(query: str, context_text: str) -> float:
    """
    Fraction of query content-words that appear in the retrieved context.
    Proxy metric for retrieval relevance (used in logging).
    """
    qwords = {
        w.lower() for w in re.findall(r"\b[a-z]{3,}\b", query.lower())
        if w not in _STOP
    }
    if not qwords:
        return 1.0
    ctx_lower = context_text.lower()
    found = sum(1 for w in qwords if w in ctx_lower)
    return round(found / len(qwords), 3)
