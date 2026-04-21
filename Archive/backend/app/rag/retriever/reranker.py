from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult


def rerank(
    query: str,
    query_embedding: list,
    results: List["SearchResult"],
) -> List["SearchResult"]:
    """
    Lightweight score-based reranker (no external model required).

    Normalises ES scores to [0, 1] and sorts descending.  The combined
    BM25 + KNN score from Elasticsearch already reflects both lexical and
    semantic relevance; normalisation makes the final scores comparable
    across queries.
    """
    if not results:
        return results

    scores = [r.score for r in results]
    min_s = min(scores)
    max_s = max(scores)

    if max_s == min_s:
        return results

    spread = max_s - min_s
    for r in results:
        r.score = round((r.score - min_s) / spread, 4)

    results.sort(key=lambda r: r.score, reverse=True)
    return results
