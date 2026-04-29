from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

from app.rag.embedding.embedder import get_embeddings
from app.rag.retriever.query_parser import parse_query, detect_query_intent
from app.rag.retriever.reranker import rerank
from app.rag.vector_store.elastic_store import (
    hybrid_search,
    get_all_list_items_by_category,
    fetch_parents_by_ids,
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

    # Parent-child fields (None for old flat chunks — backward compatible)
    parent_id:        Optional[str]  = None
    child_id:         Optional[str]  = None
    page_range_start: Optional[int]  = None
    page_range_end:   Optional[int]  = None
    _parent_doc:      Optional[dict] = field(default=None, repr=False)
    # _parent_doc is populated by search() after fetch_parents_by_ids()

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
            doc_id           = src.get("doc_id", 0),
            content          = src.get("content", ""),
            score            = float(hit.get("_score") or 0.0),
            page_number      = src.get("page_number", 1),
            chunk_index      = src.get("chunk_index", 0),
            heading          = src.get("heading", ""),
            file_name        = src.get("file_name", ""),
            branch           = src.get("branch", ""),
            doc_type         = src.get("doc_type", ""),
            year             = src.get("year"),
            section          = src.get("section", ""),
            hq_id            = src.get("hq_id"),
            unit_id          = src.get("unit_id"),
            command          = src.get("command"),
            description      = src.get("description"),
            rank_in_section  = src.get("rank_in_section"),
            category         = src.get("category"),
            is_list_item     = src.get("is_list_item", False),
            # Parent-child fields (None for old flat chunks)
            parent_id        = src.get("parent_id"),
            child_id         = src.get("child_id"),
            page_range_start = src.get("page_range_start"),
            page_range_end   = src.get("page_range_end"),
        ))
    return results


def parallel_search(
    query:   str,
    filters: dict | None = None,
    top_k:   int = 5,
    user=None,
    n_variants: int = 3,
) -> List[SearchResult]:
    """
    Multi-query parallel retrieval.

    1. Expand query into n_variants variants (heuristic + Ollama optional).
    2. Embed all variants in one batch call.
    3. Run hybrid_search for each variant concurrently (ThreadPool).
    4. Merge all hits, deduplicate by ES _id (keep highest score).
    5. Return top_k unique children.

    Falls back to single-query search if variant generation fails.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.rag.llm.query_rewriter import generate_query_variants
    from app.rag.retriever.rbac_filter import build_rbac_filter

    rbac_clauses = build_rbac_filter(user)

    # ── 1. Generate query variants ────────────────────────────────────────
    try:
        extra = generate_query_variants(query, n=n_variants - 1) if n_variants > 1 else []
    except Exception:
        extra = []
    variants = [query] + extra[:n_variants - 1]

    # ── 2. Batch-embed all variants ───────────────────────────────────────
    try:
        embeddings = get_embeddings(variants)
    except Exception as e:
        print(f"[RETRIEVER] parallel embed failed ({e}), falling back to single query")
        embeddings = get_embeddings([query])
        variants   = [query]

    # ── 3. Parallel ES searches ───────────────────────────────────────────
    retrieve_k = top_k * 4

    def _one_search(text: str, emb: list[float]) -> list[dict]:
        return hybrid_search(
            query_text=text,
            query_embedding=emb,
            filters=filters,
            top_k=retrieve_k,
            rbac_clauses=rbac_clauses or None,
        )

    all_hits: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(variants)) as pool:
        futures = [pool.submit(_one_search, v, e) for v, e in zip(variants, embeddings)]
        for fut in futures:
            try:
                all_hits.extend(fut.result())
            except Exception as e:
                print(f"[RETRIEVER] parallel search shard error: {e}")

    # ── 4. Deduplicate by ES _id, keep highest score ──────────────────────
    seen: dict[str, dict] = {}
    for hit in all_hits:
        _id = hit.get("_id", "")
        if _id not in seen or (hit.get("_score") or 0) > (seen[_id].get("_score") or 0):
            seen[_id] = hit

    deduped = sorted(seen.values(), key=lambda h: -(h.get("_score") or 0))
    return _hits_to_results(deduped[:top_k])


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

    # ── Stage 3: Query expansion ──────────────────────────────────────────
    print("🔎 [2] Rewriting query")
    search_text, _ = rewrite_query(
        query=clean_query, intent=intent,
        use_hyde=False, use_expansion=True,
    )
    print(f"🔎 Search text : {search_text!r}")

    # ── Stage 4+5: Parallel multi-query search + dedup ───────────────────
    # parallel_search() embeds all variants in one batch, runs 3 parallel
    # ES queries, merges hits (highest score per _id), returns top candidates.
    print("🔎 [3] Parallel multi-query search")
    results = parallel_search(
        query=search_text,
        filters=effective_filters or None,
        top_k=top_k * 4,    # large pool before reranking
        user=user,
        n_variants=3,
    )

    # ── Zero-result fallback (strip content filters, keep RBAC) ──────────
    if not results and effective_filters:
        print("🔎 [3a] 0 results with filters — retrying without content filters")
        results = parallel_search(
            query=search_text, filters=None,
            top_k=top_k * 4, user=user, n_variants=2,
        )
        if results:
            print(f"🔎 Fallback found {len(results)} results (no content filters)")

    if not results:
        print("🔎 No results found")
        return []

    print(f"🔎 {len(results)} candidates after parallel search + dedup")

    # ── Stage 6: Embed for reranker ───────────────────────────────────────
    print("🔎 [4] Reranking")
    emb_for_rerank = get_embeddings([search_text])
    results = rerank(
        query=search_text,
        query_embedding=emb_for_rerank[0],
        results=results,
        intent=intent,
    )

    final = results[:top_k]

    # ── Stage 7: Fetch parent sections for new parent-child docs ─────────
    # For results that have a parent_id (new ingestion format), retrieve the
    # full section text from ES and attach it as _parent_doc.
    # Results from old flat ingestion (parent_id=None) are unchanged.
    parent_ids = list({r.parent_id for r in final if r.parent_id})
    if parent_ids:
        print(f"🔎 [5] Fetching {len(parent_ids)} parent section(s)")
        parents = fetch_parents_by_ids(parent_ids)
        pid_map = {p["parent_id"]: p for p in parents}
        for r in final:
            if r.parent_id and r.parent_id in pid_map:
                r._parent_doc = pid_map[r.parent_id]

    print(f"🔎 Returning {len(final)} results")
    return final
