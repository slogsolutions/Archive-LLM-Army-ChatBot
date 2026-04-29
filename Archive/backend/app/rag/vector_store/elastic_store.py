
# IMPROVED VERSION 

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
                },
                "command_analyzer": {
                    "type": "custom",
                    "tokenizer": "keyword",  # Keep "ls -al" as one token
                    "filter": ["lowercase"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            # ========== CORE CONTENT ==========
            "doc_id":          {"type": "integer"},
            "content":         {
                "type": "text",
                "analyzer": "doc_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"}
                }
            },
            "embedding": {
                "type":       "dense_vector",
                "dims":        EMBEDDING_DIM,
                "index":       True,
                "similarity":  "cosine",
            },

            # ========== 🔥 COMMAND METADATA (NEW) ==========
            "command": {
                "type": "text",
                "analyzer": "command_analyzer",
                "fields": {
                    "keyword": {"type": "keyword"}  # Exact match: "ls -al"
                }
            },
            "description": {
                "type": "text",
                "analyzer": "doc_analyzer"
            },
            "rank_in_section": {
                "type": "integer"  # Position: 1, 2, 3...
            },
            "category": {
                "type": "keyword"  # file_commands, process_mgmt, network...
            },
            "section": {
                "type": "keyword"  # "File Commands", "Process Management"
            },
            "is_list_item": {
                "type": "boolean"  # true if from numbered list, false if prose
            },

            # ========== CHUNK POSITIONING ==========
            "page_number":     {"type": "integer"},
            "chunk_index":     {"type": "integer"},
            "total_chunks":    {"type": "integer"},
            "heading":         {"type": "text"},
            "char_offset":     {"type": "integer"},

            # ========== DOCUMENT METADATA ==========
            "file_name":       {"type": "keyword"},
            "file_type":       {"type": "keyword"},
            "branch":          {"type": "keyword"},
            "unit_id":         {"type": "integer"},
            "hq_id":           {"type": "integer"},
            "doc_type":        {"type": "keyword"},
            "year":            {"type": "integer"},

            # ========== DOCUMENT TITLE (extracted from PDF header) ==========
            "doc_title": {
                "type": "text",
                "analyzer": "doc_analyzer",
            },

            # ========== KEYWORDS (user-supplied + auto-extracted) ==========
            "keywords": {
                "type": "text",
                "analyzer": "doc_analyzer",
            },

            # ========== PARENT-CHILD STRUCTURE ==========
            # is_parent=true  → parent/section doc (no embedding, has full_section_text)
            # is_parent=false → child/chunk doc   (has embedding, has parent_id)
            # Old flat chunks (no is_parent field) are treated as children by default.
            "is_parent":         {"type": "boolean"},
            "parent_id":         {"type": "keyword"},   # "P_{doc_id}_{section_idx}"
            "child_id":          {"type": "keyword"},   # "C_{doc_id}_{section_idx}_{child_idx}"
            "full_section_text": {"type": "text", "analyzer": "doc_analyzer"},
            "page_range_start":  {"type": "integer"},
            "page_range_end":    {"type": "integer"},
            "child_count":       {"type": "integer"},
            "section_order":     {"type": "integer"},

            # ========== ACCESS CONTROL ==========
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
    
    🔥 NEW: Supports command-specific queries.

    Uses ES 8.x top-level `query` + `knn` parameters which are combined
    automatically by Elasticsearch into a single ranked result list.

    Args:
        query_text:      natural language query string
        query_embedding: dense embedding vector for the query
        filters:         optional dict {branch, doc_type, year, section, hq_id, unit_id, 
                                        command, category, rank_in_section}
        top_k:           number of results to return
        rbac_clauses:    extra ES filter clauses from RBAC (list of dicts)
        es:              optional existing ES client

    Returns:
        List of raw ES hit dicts (each has '_score' and '_source').
    
    Examples:
        # Get all file commands
        results = hybrid_search("ls", embedding, filters={"category": "file_commands"})
        
        # Get command #5 in File Commands section
        results = hybrid_search("", embedding, filters={
            "section": "File Commands",
            "rank_in_section": 5
        })
        
        # Exact command match
        results = hybrid_search("ls -al", embedding, filters={"command.keyword": "ls -al"})
    """
    if es is None:
        es = get_es()

    # Build filter clause list
    filter_clauses: list[dict] = []

    if filters:
        _add_term(filter_clauses, "branch",           filters.get("branch"))
        _add_term(filter_clauses, "doc_type",         filters.get("doc_type"))
        _add_term(filter_clauses, "year",             filters.get("year"))
        _add_term(filter_clauses, "section",          filters.get("section"))
        _add_term(filter_clauses, "hq_id",            filters.get("hq_id"))
        _add_term(filter_clauses, "unit_id",          filters.get("unit_id"))
        
        # 🔥 NEW command-specific filters
        _add_term(filter_clauses, "category",         filters.get("category"))
        _add_term(filter_clauses, "rank_in_section",  filters.get("rank_in_section"))
        _add_term(filter_clauses, "command.keyword",  filters.get("command"))

    if rbac_clauses:
        filter_clauses.extend(rbac_clauses)

    # Always search CHILD chunks only (is_parent=false or null for old flat chunks).
    # Parent docs are fetched separately via fetch_parents_by_ids() after retrieval.
    # The `{"bool": {"should": ...}}` handles both new children and old flat chunks.
    filter_clauses.append({
        "bool": {
            "should": [
                {"term":   {"is_parent": False}},
                {"bool":   {"must_not": {"exists": {"field": "is_parent"}}}},
            ],
            "minimum_should_match": 1,
        }
    })

    # BM25 text query — multi_match across content + heading + doc_title + keywords
    # Boost order: keywords (3×) > doc_title (2×) > heading (2×) > content (1×)
    bm25_query: dict = {
        "bool": {
            "must": {
                "multi_match": {
                    "query":    query_text,
                    "fields":   ["content", "heading^2", "doc_title^2", "keywords^3"],
                    "operator": "or",
                    "fuzziness": "AUTO",
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


def exact_command_search(
    command: str,
    filters: dict | None = None,
    es: Elasticsearch = None,
) -> list[dict]:
    """
    Exact match search for a specific command (no fuzzy matching).
    
    Args:
        command: "ls -al" (must match exactly)
        filters: additional filters (section, category, etc.)
        es:      optional ES client
    
    Returns:
        List of matching documents.
    
    Example:
        results = exact_command_search("ls -al", filters={"section": "File Commands"})
    """
    if es is None:
        es = get_es()
    
    filter_clauses = []
    _add_term(filter_clauses, "command.keyword", command)
    
    if filters:
        _add_term(filter_clauses, "section", filters.get("section"))
        _add_term(filter_clauses, "category", filters.get("category"))
    
    query = {
        "bool": {
            "filter": filter_clauses
        }
    }
    
    try:
        resp = es.search(
            index=INDEX_NAME,
            query=query,
            size=10,
            _source=True,
        )
        return resp["hits"]["hits"]
    except Exception as e:
        print(f"[ES] Exact search error: {e}")
        return []


def get_section_commands(
    section: str,
    category: str | None = None,
    es: Elasticsearch = None,
) -> list[dict]:
    """
    Get all commands in a section, optionally filtered by category.
    
    Args:
        section: "File Commands" or "Process Management"
        category: optional filter, e.g. "file_commands"
        es: optional ES client
    
    Returns:
        List of commands sorted by rank_in_section.
    
    Example:
        cmds = get_section_commands("File Commands")
    """
    if es is None:
        es = get_es()
    
    filter_clauses = [{"term": {"section": section}}, {"term": {"is_list_item": True}}]
    
    if category:
        filter_clauses.append({"term": {"category": category}})
    
    query = {
        "bool": {
            "filter": filter_clauses
        }
    }
    
    try:
        resp = es.search(
            index=INDEX_NAME,
            query=query,
            size=100,
            sort=[{"rank_in_section": "asc"}],
            _source=True,
        )
        return resp["hits"]["hits"]
    except Exception as e:
        print(f"[ES] Section search error: {e}")
        return []


def get_all_list_items_by_category(
    category: str,
    rbac_clauses: list | None = None,
    es: Elasticsearch = None,
) -> list[dict]:
    """
    Fetch ALL indexed list items for a given category, sorted by rank.
    Used by the retriever for "list all X" queries instead of hybrid search.
    Returns up to 200 items (enough for any realistic command list).
    """
    if es is None:
        es = get_es()

    filter_clauses: list[dict] = [
        {"term": {"is_list_item": True}},
        {"term": {"category": category}},
    ]
    if rbac_clauses:
        filter_clauses.extend(rbac_clauses)

    query = {"bool": {"filter": filter_clauses}}

    try:
        resp = es.search(
            index=INDEX_NAME,
            query=query,
            size=200,
            sort=[{"doc_id": "asc"}, {"rank_in_section": "asc"}],
            _source=True,
        )
        return resp["hits"]["hits"]
    except Exception as e:
        print(f"[ES] get_all_list_items_by_category error: {e}")
        return []


def fetch_parents_by_ids(
    parent_ids: list[str],
    es: Elasticsearch = None,
) -> list[dict]:
    """
    Fetch full parent/section documents by parent_id after child retrieval.
    Returns the _source of each parent doc (includes full_section_text,
    heading, page_range_start/end, doc_id, file_name, etc.).
    Called by retriever.search() when use_parent_child=True.
    """
    if not parent_ids:
        return []
    if es is None:
        es = get_es()

    try:
        resp = es.search(
            index=INDEX_NAME,
            query={
                "bool": {
                    "filter": [
                        {"term":  {"is_parent": True}},
                        {"terms": {"parent_id": parent_ids}},
                    ]
                }
            },
            size=min(len(parent_ids) + 10, 50),
            _source=[
                "parent_id", "heading", "full_section_text",
                "page_range_start", "page_range_end", "section_order",
                "doc_id", "file_name", "doc_type", "branch", "year",
                "doc_title", "child_count",
            ],
        )
        return [h["_source"] for h in resp["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] fetch_parents_by_ids error: {e}")
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
    """Add term filter if value is not None/empty."""
    if value is not None and value != "":
        clauses.append({"term": {field: value}})