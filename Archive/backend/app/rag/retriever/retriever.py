from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from app.rag.embedding.embedder import get_embeddings
from app.rag.retriever.query_parser import parse_query, detect_query_intent
from app.rag.retriever.reranker import rerank
from app.rag.vector_store.elastic_store import (
    hybrid_search,
    get_all_list_items_by_category,
)
from app.rag.llm.query_rewriter import rewrite_query


@dataclass
class SearchResult:
    # Core content
    doc_id: int
    content: str
    score: float

    # Chunk positioning
    page_number: int
    chunk_index: int
    heading: str

    # Document metadata
    file_name: str
    branch: str
    doc_type: str
    year: Optional[int]
    section: str
    hq_id: Optional[int]
    unit_id: Optional[int]

    # Command-specific fields
    command: Optional[str] = None
    description: Optional[str] = None
    rank_in_section: Optional[int] = None
    category: Optional[str] = None
    is_list_item: bool = False

    def get_display_title(self) -> str:
        if self.is_list_item and self.command:
            rank_str     = f"#{self.rank_in_section}" if self.rank_in_section else ""
            category_str = f", {self.category}" if self.category else ""
            return f"{self.command} (command {rank_str}{category_str})"
        elif self.heading:
            return f"{self.heading} (page {self.page_number})"
        else:
            preview = self.content[:80] + "..." if len(self.content) > 80 else self.content
            return preview


def _hits_to_results(hits: list[dict]) -> List[SearchResult]:
    results: List[SearchResult] = []
    for hit in hits:
        src = hit.get("_source", {})
        results.append(SearchResult(
            doc_id          = src.get("doc_id", 0),
            content         = src.get("content", ""),
            score           = float(hit.get("_score") or 0.0),
            page_number     = src.get("page_number", 1),
            chunk_index     = src.get("chunk_index", 0),
            heading         = src.get("heading", ""),
            file_name       = src.get("file_name", ""),
            branch          = src.get("branch", ""),
            doc_type        = src.get("doc_type", ""),
            year            = src.get("year"),
            section         = src.get("section", ""),
            hq_id           = src.get("hq_id"),
            unit_id         = src.get("unit_id"),
            command         = src.get("command"),
            description     = src.get("description"),
            rank_in_section = src.get("rank_in_section"),
            category        = src.get("category"),
            is_list_item    = src.get("is_list_item", False),
        ))
    return results


def search(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
    user=None,
) -> List[SearchResult]:
    """
    Full retrieval pipeline: parse → rewrite → embed → search → rerank.

    For "list" intent with a category filter, bypasses hybrid search and
    fetches ALL indexed list items of that category via a direct ES query,
    so the LLM can enumerate every entry rather than just top-5.

    Falls back to hybrid search without filters if the filtered query
    returns zero results (prevents silent failures when category filter
    is too strict for the current index state).
    """
    if not query or not query.strip():
        return []

    # ── Stage 1: Parse & intent ───────────────────────────────────────────
    print("🔎 [1] Parsing query")
    parsed      = parse_query(query)
    clean_query = parsed["query"]
    intent      = detect_query_intent(query)
    print(f"🔎 Clean query : {clean_query!r}")
    print(f"🔎 Filters     : {parsed['filters']}")
    print(f"🔎 Intent      : {intent}")

    # Merge inline filters with explicit caller filters (explicit win)
    effective_filters: dict = {**parsed["filters"]}
    for k, v in (filters or {}).items():
        if v is not None and v != "":
            effective_filters[k] = v

    # ── RBAC ─────────────────────────────────────────────────────────────
    from app.rag.retriever.rbac_filter import build_rbac_filter
    rbac_clauses = build_rbac_filter(user)

    # ── Stage 2: List-all fast path ───────────────────────────────────────
    # When user wants a full enumeration ("list all file commands"), skip
    # hybrid search and fetch every indexed item for that category in rank
    # order.  This guarantees we return ALL items, not just top-K by score.
    if intent == "list" and effective_filters.get("category"):
        category = effective_filters["category"]
        print(f"🔎 [2] List-all path for category={category!r}")
        list_hits = get_all_list_items_by_category(
            category=category,
            rbac_clauses=rbac_clauses or None,
        )
        if list_hits:
            print(f"🔎 List-all found {len(list_hits)} items")
            results = _hits_to_results(list_hits)
            # Score uniformly (already sorted by rank from ES)
            for i, r in enumerate(results):
                r.score = 1.0 - i * 0.01  # tiny decreasing score preserves rank order
            return results
        print("🔎 List-all returned 0 — falling back to hybrid search")

    # ── Stage 3: Query rewriting + HyDE ──────────────────────────────────
    print("🔎 [2] Rewriting query")
    search_text, hyde_passage = rewrite_query(
        query=clean_query,
        intent=intent,
        use_hyde=True,
        use_expansion=True,
    )
    print(f"🔎 Search text : {search_text!r}")
    print(f"🔎 HyDE        : {'yes' if hyde_passage else 'no'}")

    # ── Stage 4: Embed ────────────────────────────────────────────────────
    print("🔎 [3] Embedding")
    embed_text   = hyde_passage if hyde_passage else search_text
    embeddings   = get_embeddings([embed_text])
    query_vector = embeddings[0]

    # ── Stage 5: Hybrid search ─────────────────────────────────────────────
    # Retrieve 2× top_k as headroom for the reranker.
    # For list intent retrieve more candidates so the LLM gets full lists.
    retrieve_k = top_k * 4 if intent == "list" else top_k * 2
    print("🔎 [4] Hybrid search")

    hits = hybrid_search(
        query_text=search_text,
        query_embedding=query_vector,
        filters=effective_filters or None,
        top_k=retrieve_k,
        rbac_clauses=rbac_clauses or None,
    )

    # ── Zero-result fallback ──────────────────────────────────────────────
    # If the filtered query found nothing, retry without content filters
    # (keep RBAC).  This prevents silent failures when the category/section
    # filter is stricter than the current index state.
    if not hits and effective_filters:
        print("🔎 [4a] 0 results with filters — retrying without content filters")
        hits = hybrid_search(
            query_text=search_text,
            query_embedding=query_vector,
            filters=None,
            top_k=retrieve_k,
            rbac_clauses=rbac_clauses or None,
        )
        if hits:
            print(f"🔎 Fallback found {len(hits)} results (no content filters)")

    if not hits:
        print("🔎 No results found")
        return []

    print(f"🔎 ES hits: {len(hits)}")

    results = _hits_to_results(hits)

    # ── Stage 6: Rerank ───────────────────────────────────────────────────
    print("🔎 [5] Reranking")
    results = rerank(
        query=search_text,
        query_embedding=query_vector,
        results=results,
        intent=intent,
    )

    final = results[:top_k]
    print(f"🔎 Returning {len(final)} results")
    return final
