from __future__ import annotations
"""
hybrid_search — tolerant multi-field version.

KEY FIX vs previous version
----------------------------
Old BM25 only searched the `content` field.
So "show all file commands" matched nothing because the Linux PDF
content says "Unix/Linux Command Reference File Commands Is Directory..."
not "file commands" directly.

New BM25 uses multi_match across:
    content    (main text)
    doc_type   (e.g. "Linux Command List")
    section    (e.g. "Part 1")
    heading    (e.g. "File Commands")

This means "file commands" now also matches doc_type="Linux Command List"
and any heading field, dramatically improving recall.

RBAC
----
hq_id and unit_id remain the ONLY hard filters.
Everything else is a soft boost.
"""

from app.rag.vector_store.elastic_store import get_es, INDEX_NAME
from elasticsearch import Elasticsearch


def hybrid_search(
    query_text: str,
    query_embedding: list,
    filters: dict | None = None,
    top_k: int = 10,
    rbac_clauses: list | None = None,
    es: Elasticsearch = None,
) -> list[dict]:
    if es is None:
        es = get_es()

    filters = filters or {}

    # ── RBAC hard filters (the ONLY must-match clauses) ───────────────────
    hard_clauses: list[dict] = []
    if rbac_clauses:
        hard_clauses.extend(rbac_clauses)

    # ── Soft boost clauses ────────────────────────────────────────────────
    boost_clauses: list[dict] = []

    if filters.get("branch"):
        boost_clauses.append({"term": {"branch":   {"value": filters["branch"],   "boost": 2.0}}})
    if filters.get("doc_type"):
        boost_clauses.append({"term": {"doc_type": {"value": filters["doc_type"], "boost": 2.0}}})
    if filters.get("year"):
        boost_clauses.append({"term": {"year":     {"value": filters["year"],     "boost": 1.5}}})
    if filters.get("section"):
        boost_clauses.append({"term": {"section":  {"value": filters["section"],  "boost": 2.0}}})
    if filters.get("command"):
        boost_clauses.append({"term": {"command.keyword": {"value": filters["command"], "boost": 4.0}}})
    if filters.get("rank_in_section") is not None:
        boost_clauses.append({"term": {"rank_in_section": {"value": filters["rank_in_section"], "boost": 3.0}}})
        boost_clauses.append({"term": {"is_list_item":    {"value": True,  "boost": 1.5}}})
    if filters.get("category"):
        boost_clauses.append({"term": {"category": {"value": filters["category"], "boost": 2.0}}})
        boost_clauses.append({"term": {"is_list_item": {"value": True, "boost": 1.5}}})

    # ── BM25 — multi-field so "file commands" hits doc_type + heading too ─
    bool_query: dict = {}

    if query_text and query_text.strip():
        bool_query["must"] = {
            "multi_match": {
                "query":  query_text,
                "fields": [
                    "content^1.0",    # main text — base weight
                    "doc_type^2.0",   # e.g. "Linux Command List" — strong signal
                    "section^1.5",    # e.g. "File Commands"
                    "heading^1.5",    # section heading
                    "description^1.5" # command description (after re-index)
                ],
                "type":      "best_fields",
                "operator":  "or",
                "fuzziness": "AUTO",
            }
        }
    else:
        bool_query["must"] = {"match_all": {}}

    if hard_clauses:
        bool_query["filter"] = hard_clauses

    if boost_clauses:
        bool_query["should"] = boost_clauses
        bool_query["minimum_should_match"] = 0

    bm25_query = {"bool": bool_query}

    # ── KNN ───────────────────────────────────────────────────────────────
    knn_query: dict = {
        "field":          "embedding",
        "query_vector":   query_embedding,
        "k":              min(top_k * 2, 50),
        "num_candidates": min(top_k * 10, 500),
    }
    if hard_clauses:
        knn_query["filter"] = {"bool": {"filter": hard_clauses}}

    try:
        resp = es.search(
            index=INDEX_NAME,
            query=bm25_query,
            knn=knn_query,
            size=top_k,
            _source=True,
        )
        return resp["hits"]["hits"]
    except Exception as e:
        print(f"[ES] Search error: {e}")
        return []