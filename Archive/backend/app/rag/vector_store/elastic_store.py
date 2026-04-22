from __future__ import annotations
import os
from dotenv import load_dotenv
from pathlib import Path
from elasticsearch import Elasticsearch

load_dotenv(dotenv_path=Path(__file__).resolve().parents[4] / ".env")

INDEX_NAME = "army_documents"
# Dimension must match the local embedding model (BAAI/bge-base-en = 768)
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


_INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "doc_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "stop"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "doc_id":          {"type": "integer"},
            "content":         {"type": "text", "analyzer": "doc_analyzer"},
            "embedding": {
                "type":       "dense_vector",
                "dims":        EMBEDDING_DIM,
                "index":       True,
                "similarity":  "cosine",
            },
            # --- filterable keyword fields ---
            "file_name":       {"type": "keyword"},
            "file_type":       {"type": "keyword"},
            "branch":          {"type": "keyword"},
            "unit_id":         {"type": "integer"},
            "hq_id":           {"type": "integer"},
            "doc_type":        {"type": "keyword"},
            "year":            {"type": "integer"},
            "section":         {"type": "keyword"},
            # --- chunk position ---
            "page_number":     {"type": "integer"},
            "chunk_index":     {"type": "integer"},
            "total_chunks":    {"type": "integer"},
            "heading":         {"type": "text"},
            # --- access control ---
            "uploaded_by":     {"type": "integer"},
            "min_visible_rank":{"type": "integer"},
            "created_at":      {"type": "date"},
        }
    },
}


def get_es() -> Elasticsearch:
    return Elasticsearch(os.getenv("ES_URL", "http://localhost:9200"))


def ensure_index(es: Elasticsearch = None, dim: int = None) -> Elasticsearch:
    """Create the index with explicit mapping if it does not exist yet."""
    if es is None:
        es = get_es()

    mapping = _INDEX_MAPPING
    
    
    if dim and dim != EMBEDDING_DIM:
        import copy
        mapping = copy.deepcopy(_INDEX_MAPPING)
        mapping["mappings"]["properties"]["embedding"]["dims"] = dim

    if not es.indices.exists(index=INDEX_NAME):
        es.indices.create(index=INDEX_NAME, body=mapping)
        print(f"[ES] Created index '{INDEX_NAME}' with dim={dim or EMBEDDING_DIM}")
        

    return es


def hybrid_search(
    query_text: str,
    query_embedding: list,
    filters: dict | None = None,
    top_k: int = 10,
    rbac_clauses: list | None = None,
    es: Elasticsearch = None,
) -> list[dict]:
    """
    Hybrid BM25 + KNN search on 'army_documents'.

    Uses ES 8.x top-level `query` + `knn` parameters which are combined
    automatically by Elasticsearch into a single ranked result list.

    Args:
        query_text:      natural language query string
        query_embedding: dense embedding vector for the query
        filters:         optional dict {branch, doc_type, year, section, hq_id, unit_id}
        top_k:           number of results to return
        rbac_clauses:    extra ES filter clauses from RBAC (list of dicts)
        es:              optional existing ES client

    Returns:
        List of raw ES hit dicts (each has '_score' and '_source').
    """
    if es is None:
        es = get_es()

    # Build filter clause list
    filter_clauses: list[dict] = []

    if filters:
        _add_term(filter_clauses, "branch",   filters.get("branch"))
        _add_term(filter_clauses, "doc_type", filters.get("doc_type"))
        _add_term(filter_clauses, "year",     filters.get("year"))
        _add_term(filter_clauses, "section",  filters.get("section"))
        _add_term(filter_clauses, "hq_id",    filters.get("hq_id"))
        _add_term(filter_clauses, "unit_id",  filters.get("unit_id"))

    if rbac_clauses:
        filter_clauses.extend(rbac_clauses)

    # BM25 text query
    bm25_query: dict = {
        "bool": {
            "must": {
                "match": {
                    "content": {
                        "query": query_text,
                        "operator": "or",
                        "fuzziness": "AUTO",
                    }
                }
            },
        }
    }
    if filter_clauses:
        bm25_query["bool"]["filter"] = filter_clauses

    # KNN vector query
    knn_query: dict = {
        "field": "embedding",
        "query_vector": query_embedding,
        "k": min(top_k * 2, 50),
        "num_candidates": min(top_k * 10, 500),
    }
    if filter_clauses:
        knn_query["filter"] = {"bool": {"filter": filter_clauses}}

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


def delete_doc_chunks(doc_id: int, es: Elasticsearch = None) -> None:
    """Remove all previously indexed chunks for a given doc_id."""
    if es is None:
        es = get_es()
    try:
        es.delete_by_query(
            index=INDEX_NAME,
            body={"query": {"term": {"doc_id": doc_id}}},
            refresh=True,
        )
    except Exception as e:
        print(f"[ES] delete_doc_chunks error: {e}")


def _add_term(clauses: list, field: str, value) -> None:
    if value is not None and value != "":
        clauses.append({"term": {field: value}})
