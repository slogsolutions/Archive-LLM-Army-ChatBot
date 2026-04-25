from __future__ import annotations
"""
Retrieval and answer quality metrics — all offline, no external services.

Retrieval metrics (require ground-truth relevant doc_ids):
    recall_at_k    fraction of relevant docs found in top-K results
    mrr            mean reciprocal rank (position of first relevant doc)
    ndcg_at_k      normalised discounted cumulative gain

Answer quality metrics:
    keyword_coverage   fraction of expected keywords present in the answer
    lexical_faithfulness  fraction of answer words traceable to context
"""
from __future__ import annotations
import math
import re
from typing import List


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def recall_at_k(retrieved_ids: List[int], relevant_ids: List[int], k: int) -> float:
    """Fraction of relevant doc_ids that appear in the top-K retrieved."""
    if not relevant_ids:
        return 0.0
    top_k  = set(retrieved_ids[:k])
    hits   = sum(1 for rid in relevant_ids if rid in top_k)
    return hits / len(relevant_ids)


def mrr(retrieved_ids: List[int], relevant_ids: List[int]) -> float:
    """Mean Reciprocal Rank — reciprocal of the rank of the first relevant doc."""
    relevant_set = set(relevant_ids)
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: List[int], relevant_ids: List[int], k: int) -> float:
    """Normalised Discounted Cumulative Gain at K (binary relevance)."""
    relevant_set = set(relevant_ids)

    def dcg(ids: List[int]) -> float:
        return sum(
            1.0 / math.log2(i + 2)
            for i, rid in enumerate(ids[:k])
            if rid in relevant_set
        )

    actual = dcg(retrieved_ids)
    ideal  = dcg(list(relevant_set)[:k])
    return actual / ideal if ideal > 0 else 0.0


# ---------------------------------------------------------------------------
# Answer quality metrics
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "will", "would", "could",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "it", "its", "this", "that", "and", "or", "not", "but",
    "if", "so", "no", "per", "via", "each", "any", "all",
}


def keyword_coverage(answer: str, expected_keywords: List[str]) -> float:
    """
    Fraction of expected_keywords that appear anywhere in the answer
    (case-insensitive substring match).
    """
    if not expected_keywords:
        return 1.0
    lower = answer.lower()
    hits  = sum(1 for kw in expected_keywords if kw.lower() in lower)
    return hits / len(expected_keywords)


def lexical_faithfulness(answer: str, context: str) -> float:
    """
    Fraction of content words in the answer that appear in the context.
    Mirrors the production faithfulness_guard lexical check.
    """
    ctx_words = (
        set(re.findall(r"\b[a-z]{3,}\b", context.lower())) - _STOPWORDS
    )
    ans_words = [
        w for w in re.findall(r"\b[a-z]{3,}\b", answer.lower())
        if w not in _STOPWORDS
    ]
    if not ans_words:
        return 0.0
    return sum(1 for w in ans_words if w in ctx_words) / len(ans_words)


def precision_at_k(retrieved_ids: List[int], relevant_ids: List[int], k: int) -> float:
    """Fraction of top-K retrieved docs that are relevant."""
    if not retrieved_ids:
        return 0.0
    relevant_set = set(relevant_ids)
    top_k_hits   = sum(1 for rid in retrieved_ids[:k] if rid in relevant_set)
    return top_k_hits / min(k, len(retrieved_ids))
