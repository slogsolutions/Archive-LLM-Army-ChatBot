from __future__ import annotations
"""
Faithfulness Guard — Stage 9 of the pipeline.

Checks whether the LLM's answer is grounded in the retrieved context
before it is returned to the user.

Two modes:
  1. Fast lexical check  — keyword overlap (no extra LLM call, ~1 ms)
  2. LLM verification   — second llama3 call judges faithfulness (~5-15 s)

In production:
  - Always run the fast check (free).
  - Run LLM verification only when fast check score is below threshold
    (saves time when the answer is clearly grounded).
"""

import re
import requests
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FaithfulnessResult:
    """
    Output of the faithfulness check.

    Attributes
    ----------
    is_faithful     : True if answer appears grounded in context
    confidence      : 0.0 – 1.0 (higher = more grounded)
    method          : "lexical" | "llm"
    warning         : Human-readable warning if not faithful
    flagged_claims  : Sentences in the answer that could not be grounded
    """
    is_faithful:    bool
    confidence:     float
    method:         str
    warning:        str = ""
    flagged_claims: List[str] = None

    def __post_init__(self):
        if self.flagged_claims is None:
            self.flagged_claims = []


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Lexical: fraction of answer content-words that appear in context.
# Raised from 0.35 → 0.45 to reduce false escalations to the LLM check
# (which adds 30-60s latency on CPU).
LEXICAL_THRESHOLD = 0.45

LLM_FAITHFULNESS_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_faithfulness(
    answer: str,
    results: List["SearchResult"],
    run_llm_check: bool = True,
    model: str = "llama3:latest",
) -> FaithfulnessResult:
    """
    Check whether `answer` is grounded in the retrieved `results`.

    Pipeline:
      1. Fast lexical check → if clearly faithful, return immediately
      2. If ambiguous and run_llm_check=True → call llama3 to verify

    Args:
        answer         : LLM-generated answer text
        results        : Reranked SearchResult list used to generate answer
        run_llm_check  : Whether to call the LLM for verification
        model          : Ollama model for LLM check

    Returns:
        FaithfulnessResult
    """
    if not answer or not results:
        return FaithfulnessResult(
            is_faithful=False,
            confidence=0.0,
            method="lexical",
            warning="Empty answer or no source documents.",
        )

    # "Not found" answers: only grant a free pass when context is genuinely
    # sparse (< 200 chars total). If we retrieved substantial context but the
    # LLM still said "not available", that is a retrieval-answer mismatch
    # and must be caught by the normal checks below.
    _lower = answer.lower()
    _is_not_available = (
        "not available in the provided documents" in _lower
        or "no relevant documents" in _lower
        or "information is not available" in _lower
    )
    if _is_not_available:
        total_context_chars = sum(len(r.content) for r in results)
        if total_context_chars < 200:
            return FaithfulnessResult(is_faithful=True, confidence=1.0, method="lexical")

    # ── Fast lexical check ────────────────────────────────────────────────
    lexical_result = _lexical_check(answer, results)

    if lexical_result.confidence >= LEXICAL_THRESHOLD:
        # Clearly grounded — skip the expensive LLM call
        return lexical_result

    if not run_llm_check:
        return lexical_result

    # ── LLM faithfulness verification ─────────────────────────────────────
    print(f"[GUARD] Lexical confidence {lexical_result.confidence:.2f} — running LLM check…")
    return _llm_check(answer, results, model=model)


def safe_answer(
    answer: str,
    faithfulness: FaithfulnessResult,
) -> str:
    """
    Append a grounding warning to the answer if faithfulness is low.

    This lets the user see the answer but know it may not be reliable,
    rather than silently returning potentially hallucinated content.
    """
    if faithfulness.is_faithful:
        return answer

    disclaimer = (
        "\n\n---\n"
        "⚠️  **Grounding warning**: Part of this answer could not be "
        "verified against the source documents. Please cross-check with "
        "the original files before acting on this information."
    )
    return answer + disclaimer


# ---------------------------------------------------------------------------
# Internal: Lexical check
# ---------------------------------------------------------------------------

# Simple stopword list — don't penalise missing stopwords
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "it", "its", "this", "that", "these", "those", "and", "or",
    "but", "if", "then", "else", "when", "where", "who", "which", "what",
    "how", "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "not", "only", "same", "so", "than", "too",
    "very", "just", "because", "into", "through", "during", "before",
    "after", "above", "below", "between", "out", "off", "over", "under",
    "again", "further", "once", "per", "according",
}


def _lexical_check(
    answer: str,
    results: List["SearchResult"],
) -> FaithfulnessResult:
    """
    Keyword overlap between answer and context.

    Score = (content words in answer that appear in context) / total content words in answer

    Returns FaithfulnessResult with method="lexical".
    """
    # Build context vocabulary from all retrieved chunks
    context_text = " ".join(r.content for r in results).lower()
    context_words = set(re.findall(r"\b[a-z]{3,}\b", context_text)) - _STOPWORDS

    # Extract content words from the answer
    answer_words = [
        w for w in re.findall(r"\b[a-z]{3,}\b", answer.lower())
        if w not in _STOPWORDS
    ]

    if not answer_words:
        return FaithfulnessResult(
            is_faithful=False,
            confidence=0.0,
            method="lexical",
            warning="Answer contained no meaningful content words.",
        )

    # Overlap score
    matched   = sum(1 for w in answer_words if w in context_words)
    score     = matched / len(answer_words)
    is_ok     = score >= LEXICAL_THRESHOLD

    # Identify sentences that have low overlap (potential hallucinations)
    flagged = _find_low_overlap_sentences(answer, context_words)

    return FaithfulnessResult(
        is_faithful=is_ok,
        confidence=round(score, 3),
        method="lexical",
        warning="" if is_ok else (
            f"Only {score:.0%} of answer words found in source documents. "
            "Answer may contain information not in the retrieved context."
        ),
        flagged_claims=flagged,
    )


def _find_low_overlap_sentences(answer: str, context_words: set[str]) -> List[str]:
    """Return sentences from the answer that have < 25% word overlap with context."""
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    flagged = []
    for sent in sentences:
        words = [w for w in re.findall(r"\b[a-z]{3,}\b", sent.lower()) if w not in _STOPWORDS]
        if not words:
            continue
        overlap = sum(1 for w in words if w in context_words) / len(words)
        if overlap < 0.25:
            flagged.append(sent.strip())
    return flagged


# ---------------------------------------------------------------------------
# Internal: LLM faithfulness check
# ---------------------------------------------------------------------------

_LLM_GUARD_SYSTEM = """\
You are a faithfulness evaluator for an Indian Army RAG system.

Given:
- CONTEXT: retrieved document passages
- ANSWER: the LLM-generated answer

Determine if the ANSWER is grounded in the CONTEXT.

Respond with EXACTLY this JSON (no other text):
{
  "verdict": "faithful" | "unfaithful" | "partially_faithful",
  "confidence": 0.0-1.0,
  "reason": "one sentence explanation"
}

Rules:
- "faithful"           → all claims in ANSWER are supported by CONTEXT
- "partially_faithful" → most claims supported, minor unsupported details
- "unfaithful"         → significant claims NOT in CONTEXT (hallucination)
"""


def _llm_check(
    answer: str,
    results: List["SearchResult"],
    model: str = "llama3:latest",
) -> FaithfulnessResult:
    """Call llama3 to judge whether the answer is grounded in context."""
    context_snippet = "\n---\n".join(r.content[:300] for r in results[:5])

    prompt = (
        f"CONTEXT:\n{context_snippet}\n\n"
        f"ANSWER:\n{answer}\n\n"
        "Is the ANSWER faithful to the CONTEXT? Respond with JSON only."
    )

    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _LLM_GUARD_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 100},
            },
            timeout=180,
        )
        resp.raise_for_status()

        raw = resp.json()["message"]["content"].strip()

        # Parse JSON — strip markdown fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        import json
        data = json.loads(raw)

        verdict    = data.get("verdict", "partially_faithful")
        confidence = float(data.get("confidence", 0.5))
        reason     = data.get("reason", "")

        is_faithful = verdict in ("faithful", "partially_faithful")

        print(f"[GUARD] LLM verdict: {verdict} (confidence={confidence:.2f})")

        return FaithfulnessResult(
            is_faithful=is_faithful,
            confidence=confidence,
            method="llm",
            warning="" if is_faithful else f"LLM guard: {reason}",
        )

    except Exception as e:
        print(f"[GUARD] LLM check failed: {e} — falling back to lexical")
        return _lexical_check(answer, results)