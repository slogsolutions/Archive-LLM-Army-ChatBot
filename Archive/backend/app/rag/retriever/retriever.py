from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from app.rag.embedding.embedder import get_embeddings
from app.rag.retriever.query_parser import parse_query
from app.rag.retriever.reranker import rerank
from app.rag.vector_store.elastic_store import hybrid_search


@dataclass
class SearchResult:
    doc_id: int
    content: str
    score: float
    page_number: int
    chunk_index: int
    heading: str
    file_name: str
    branch: str
    doc_type: str
    year: Optional[int]
    section: str
    hq_id: Optional[int]
    unit_id: Optional[int]


def search(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
    user=None,
) -> List[SearchResult]:
    """
    Hybrid semantic + keyword search over the army document index.

    Pipeline:
      1. Parse query → extract inline filter hints
      2. Build RBAC filter clauses from the authenticated user
      3. Embed the query with the local SentenceTransformer model
      4. Run BM25 + KNN hybrid search in Elasticsearch
      5. Rerank by normalised combined score
      6. Return top_k results

    Args:
        query:   natural language query
        filters: explicit filters {branch, doc_type, year, section, hq_id, unit_id}
        top_k:   number of results to return
        user:    authenticated user object (used for RBAC scoping)
    """
    
    if not query or not query.strip():
        return []

    # ── 1. Parse & normalise query ─────────────────────────────────────────
    print("🔎 Step 1: Parsing query")
    
    
    parsed = parse_query(query)
    print("🔎 Clean query:", parsed["query"])
    print("🔎 Filters:", parsed["filters"])
    clean_query = parsed["query"]
    

    # Merge inline filters with explicit filters (explicit take priority)
    effective_filters: dict = {}
    for k, v in parsed["filters"].items():
        effective_filters[k] = v
    for k, v in (filters or {}).items():
        if v is not None and v != "":
            effective_filters[k] = v

    # ── 2. RBAC filter clauses ─────────────────────────────────────────────
    from app.rag.retriever.rbac_filter import build_rbac_filter
    rbac_clauses = build_rbac_filter(user)
    if user:
        rank = getattr(user, "rank_level", 6)
        # Only documents visible to this rank level
        rbac_clauses.append({"range": {"min_visible_rank": {"gte": rank}}})

        role = getattr(user, "role", "")
        if role not in ("super_admin",):
            if getattr(user, "hq_id", None):
                rbac_clauses.append({"term": {"hq_id": user.hq_id}})
        if role not in ("super_admin", "hq_admin"):
            if getattr(user, "unit_id", None):
                rbac_clauses.append({"term": {"unit_id": user.unit_id}})

    # ── 3. Embed query ─────────────────────────────────────────────────────
    print("🔎 Step 2: Generating embedding...")
    embeddings = get_embeddings([clean_query])
    query_embedding = embeddings[0]
    print("🔎 Embedding generated")

    # ── 4. Hybrid search (retrieve 2× for reranking headroom) ─────────────
    print("🔎 Step 3: Searching Elasticsearch...")
    hits = hybrid_search(
        query_text=clean_query,
        query_embedding=query_embedding,
        filters=effective_filters or None,
        top_k=top_k * 2,
        rbac_clauses=rbac_clauses or None,
    )

    if not hits:
        return []
    print("🔎 ES hits:", len(hits))
    # ── 5. Deserialise hits ────────────────────────────────────────────────
    print(" Deserialise hits")
    results: List[SearchResult] = []
    for hit in hits:
        src = hit.get("_source", {})
        results.append(SearchResult(
            doc_id=src.get("doc_id", 0),
            content=src.get("content", ""),
            score=float(hit.get("_score") or 0.0),
            page_number=src.get("page_number", 1),
            chunk_index=src.get("chunk_index", 0),
            heading=src.get("heading", ""),
            file_name=src.get("file_name", ""),
            branch=src.get("branch", ""),
            doc_type=src.get("doc_type", ""),
            year=src.get("year"),
            section=src.get("section", ""),
            hq_id=src.get("hq_id"),
            unit_id=src.get("unit_id"),
        ))
  
    # ── 6. Rerank & truncate ───────────────────────────────────────────────
    print(" Rerank & truncate")
    results = rerank(clean_query, query_embedding, results)
    return results[:top_k]
