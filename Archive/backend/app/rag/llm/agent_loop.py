from __future__ import annotations
"""
Agentic multi-hop reasoning loop — Stage 3.5 of the RAG pipeline.

When the first-pass retrieval produces an answer that is clearly insufficient
(signals "not found" / "cannot determine"), this module:

  1. Asks the LLM what specific sub-queries would fill the gap
  2. Runs those sub-queries through the standard retriever
  3. Merges, deduplicates, and re-sorts all chunks by score
  4. Returns the expanded result set to the caller for a second LLM call

Max hops: 2.  Each hop adds ~15–30 s on CPU, so avoid setting this > 3.
The agentic loop is SKIPPED for "list" intent (those queries are already
handled by the list-all fast path in retriever.py).
"""
import requests
from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult

MAX_HOPS = 2

_SUBQUERY_SYSTEM = """\
You are a search query planner for an Indian Army document system.
Given an original question and an answer that lacks sufficient information,
generate 1-2 specific follow-up search queries that would retrieve the missing
information from the document index.
Output ONLY the queries, one per line. No numbering. No explanation.
Keep each query under 15 words.
"""

_INSUFFICIENT_SIGNALS = [
    "not available in the provided documents",
    "cannot determine",
    "no information",
    "insufficient information",
    "not mentioned",
    "not specified",
    "no relevant documents found",
    "could not find",
    "unable to find",
]


def _is_insufficient(answer: str) -> bool:
    lower = answer.lower()
    return any(sig in lower for sig in _INSUFFICIENT_SIGNALS)


def _extract_sub_queries(
    original_query: str,
    answer: str,
    model: str = "llama3:latest",
) -> List[str]:
    """Use the LLM to generate targeted follow-up search queries."""
    prompt = (
        f"Original question: {original_query}\n"
        f"Insufficient answer: {answer[:300]}\n\n"
        "Generate 1-2 specific sub-queries to retrieve the missing information."
    )
    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SUBQUERY_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 80},
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw      = resp.json()["message"]["content"].strip()
        queries  = [q.strip() for q in raw.split("\n") if q.strip()][:2]
        print(f"[AGENT] Sub-queries: {queries}")
        return queries
    except Exception as e:
        print(f"[AGENT] Sub-query extraction failed: {e}")
        return []


def _dedup(results: List["SearchResult"]) -> List["SearchResult"]:
    seen: set[tuple] = set()
    out: List["SearchResult"] = []
    for r in results:
        key = (r.doc_id, r.chunk_index)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def run(
    original_query: str,
    initial_results: List["SearchResult"],
    initial_answer: str,
    filters: dict | None = None,
    user=None,
    model: str = "llama3:latest",
    intent: str = "mixed",
) -> Tuple[List["SearchResult"], int]:
    """
    Attempt multi-hop retrieval when the initial answer is insufficient.

    Args:
        original_query  : The user's original question
        initial_results : Results from the first-pass retrieval
        initial_answer  : LLM answer from the first pass
        filters         : ES filters to carry into sub-queries
        user            : Auth user for RBAC
        model           : Ollama model for sub-query generation
        intent          : Skips hops for "list" intent

    Returns:
        (merged_results, hops_executed)
    """
    # Skip for list queries — they use the list-all path instead
    if intent == "list":
        return initial_results, 0

    if not _is_insufficient(initial_answer):
        return initial_results, 0

    from app.rag.retriever.retriever import search

    all_results = list(initial_results)
    hops_done   = 0

    for _ in range(MAX_HOPS):
        sub_queries = _extract_sub_queries(original_query, initial_answer, model=model)
        if not sub_queries:
            break

        new_results: List["SearchResult"] = []
        for sq in sub_queries:
            print(f"[AGENT] Hop {hops_done + 1}: {sq!r}")
            extra = search(query=sq, filters=filters, top_k=5, user=user)
            new_results.extend(extra)

        if not new_results:
            break

        all_results = _dedup(all_results + new_results)
        all_results.sort(key=lambda r: r.score, reverse=True)
        hops_done += 1

        # Enough unique documents — stop early
        if len({r.doc_id for r in all_results}) >= 3:
            break

    if hops_done:
        print(f"[AGENT] {hops_done} hop(s) added — total chunks: {len(all_results)}")

    return all_results, hops_done
