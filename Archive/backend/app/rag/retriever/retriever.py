# from __future__ import annotations
# from dataclasses import dataclass
# from typing import List, Optional

# from app.rag.embedding.embedder import get_embeddings
# from app.rag.retriever.query_parser import parse_query
# from app.rag.retriever.reranker import rerank
# from app.rag.vector_store.elastic_store import hybrid_search


# @dataclass
# class SearchResult:
#     doc_id: int
#     content: str
#     score: float
#     page_number: int
#     chunk_index: int
#     heading: str
#     file_name: str
#     branch: str
#     doc_type: str
#     year: Optional[int]
#     section: str
#     hq_id: Optional[int]
#     unit_id: Optional[int]


# def search(
#     query: str,
#     filters: dict | None = None,
#     top_k: int = 10,
#     user=None,
# ) -> List[SearchResult]:
#     """
#     Hybrid semantic + keyword search over the army document index.

#     Pipeline:
#       1. Parse query → extract inline filter hints
#       2. Build RBAC filter clauses from the authenticated user
#       3. Embed the query with the local SentenceTransformer model
#       4. Run BM25 + KNN hybrid search in Elasticsearch
#       5. Rerank by normalised combined score
#       6. Return top_k results

#     Args:
#         query:   natural language query
#         filters: explicit filters {branch, doc_type, year, section, hq_id, unit_id}
#         top_k:   number of results to return
#         user:    authenticated user object (used for RBAC scoping)
#     """
    
#     if not query or not query.strip():
#         return []

#     # ── 1. Parse & normalise query ─────────────────────────────────────────
#     print("🔎 Step 1: Parsing query")
    
    
#     parsed = parse_query(query)
#     print("🔎 Clean query:", parsed["query"])
#     print("🔎 Filters:", parsed["filters"])
#     clean_query = parsed["query"]
    

#     # Merge inline filters with explicit filters (explicit take priority)
#     effective_filters: dict = {}
#     for k, v in parsed["filters"].items():
#         effective_filters[k] = v
#     for k, v in (filters or {}).items():
#         if v is not None and v != "":
#             effective_filters[k] = v

#     # ── 2. RBAC filter clauses ─────────────────────────────────────────────
#     from app.rag.retriever.rbac_filter import build_rbac_filter
#     rbac_clauses = build_rbac_filter(user)

#     # ── 3. Embed query ─────────────────────────────────────────────────────
#     print("🔎 Step 2: Generating embedding...")
#     embeddings = get_embeddings([clean_query])
#     query_embedding = embeddings[0]
#     print("🔎 Embedding generated")

#     # ── 4. Hybrid search (retrieve 2× for reranking headroom) ─────────────
#     print("🔎 Step 3: Searching Elasticsearch...")
#     hits = hybrid_search(
#         query_text=clean_query,
#         query_embedding=query_embedding,
#         filters=effective_filters or None,
#         top_k=top_k * 2,
#         rbac_clauses=rbac_clauses or None,
#     )

#     if not hits:
#         return []
#     print("🔎 ES hits:", len(hits))
#     # ── 5. Deserialise hits ────────────────────────────────────────────────
#     print(" Deserialise hits")
#     results: List[SearchResult] = []
#     for hit in hits:
#         src = hit.get("_source", {})
#         results.append(SearchResult(
#             doc_id=src.get("doc_id", 0),
#             content=src.get("content", ""),
#             score=float(hit.get("_score") or 0.0),
#             page_number=src.get("page_number", 1),
#             chunk_index=src.get("chunk_index", 0),
#             heading=src.get("heading", ""),
#             file_name=src.get("file_name", ""),
#             branch=src.get("branch", ""),
#             doc_type=src.get("doc_type", ""),
#             year=src.get("year"),
#             section=src.get("section", ""),
#             hq_id=src.get("hq_id"),
#             unit_id=src.get("unit_id"),
#         ))
  
#     # ── 6. Rerank & truncate ───────────────────────────────────────────────
#     print(" Rerank & truncate")
#     results = rerank(clean_query, query_embedding, results)
#     return results[:top_k]

# IMPROVED VERSION 


from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from app.rag.embedding.embedder import get_embeddings
from app.rag.retriever.query_parser import parse_query, detect_query_intent
from app.rag.retriever.reranker import rerank
from app.rag.vector_store.elastic_store import hybrid_search


@dataclass
class SearchResult:
    """
    Result from hybrid semantic + keyword search.
    
    🔥 NEW: Added command metadata fields for structured queries.
    """
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
    
    # 🔥 NEW: Command-specific fields (for ListItem results)
    command: Optional[str] = None                    # "ls -al"
    description: Optional[str] = None                # "Formatted listing..."
    rank_in_section: Optional[int] = None           # Position: 1, 2, 3...
    category: Optional[str] = None                   # "file_commands", "network"
    is_list_item: bool = False                      # True if from numbered list
    
    def get_display_title(self) -> str:
        """
        User-friendly title for this result.
        
        Examples:
            "ls -al (command #2, file_commands)"
            "Introduction to File Operations (page 5)"
        """
        if self.is_list_item and self.command:
            rank_str = f"#{self.rank_in_section}" if self.rank_in_section else ""
            category_str = f", {self.category}" if self.category else ""
            return f"{self.command} (command {rank_str}{category_str})"
        elif self.heading:
            return f"{self.heading} (page {self.page_number})"
        else:
            # Truncate content
            preview = self.content[:80] + "..." if len(self.content) > 80 else self.content
            return preview


def search(
    query: str,
    filters: dict | None = None,
    top_k: int = 10,
    user=None,
) -> List[SearchResult]:
    """
    Hybrid semantic + keyword search over the army document index.

    🔥 NEW: Now supports command-specific queries.

    Pipeline:
      1. Parse query → extract inline filter hints (including rank, category, command)
      2. Detect query intent (command vs. prose vs. list)
      3. Build RBAC filter clauses from the authenticated user
      4. Embed the query with the local SentenceTransformer model
      5. Run BM25 + KNN hybrid search in Elasticsearch
      6. Rerank by intent-aware scoring (boost command results if intent is "command")
      7. Return top_k results with metadata

    Args:
        query:   natural language query (e.g., "find command 5 in File Commands")
        filters: explicit filters {branch, doc_type, year, section, rank_in_section, category, command}
        top_k:   number of results to return
        user:    authenticated user object (used for RBAC scoping)
    
    Examples:
        results = search("show me command #2")
        results = search("list all network commands")
        results = search("what is ls -al")
    """
    
    if not query or not query.strip():
        return []

    # ── 1. Parse & normalise query ─────────────────────────────────────────
    print("🔎 Step 1: Parsing query")
    
    parsed = parse_query(query)
    print("🔎 Clean query:", parsed["query"])
    print("🔎 Filters:", parsed["filters"])
    clean_query = parsed["query"]
    
    # Detect intent (command, list, prose, mixed)
    intent = detect_query_intent(query)
    print("🔎 Intent:", intent)

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
        print("🔎 No results found")
        return []
    print("🔎 ES hits:", len(hits))
    
    # ── 5. Deserialise hits ────────────────────────────────────────────────
    print("🔎 Deserializing hits...")
    results: List[SearchResult] = []
    for hit in hits:
        src = hit.get("_source", {})
        results.append(SearchResult(
            # Core content
            doc_id=src.get("doc_id", 0),
            content=src.get("content", ""),
            score=float(hit.get("_score") or 0.0),
            
            # Chunk positioning
            page_number=src.get("page_number", 1),
            chunk_index=src.get("chunk_index", 0),
            heading=src.get("heading", ""),
            
            # Document metadata
            file_name=src.get("file_name", ""),
            branch=src.get("branch", ""),
            doc_type=src.get("doc_type", ""),
            year=src.get("year"),
            section=src.get("section", ""),
            hq_id=src.get("hq_id"),
            unit_id=src.get("unit_id"),
            
            # 🔥 NEW: Command metadata (from ListItem results)
            command=src.get("command"),
            description=src.get("description"),
            rank_in_section=src.get("rank_in_section"),
            category=src.get("category"),
            is_list_item=src.get("is_list_item", False),
        ))
  
    # ── 6. Rerank with intent-awareness ────────────────────────────────────
    print("🔎 Reranking...")
    results = rerank(
        query=clean_query,
        query_embedding=query_embedding,
        results=results,
        intent=intent,  # 🔥 Pass intent to reranker
    )
    
    print(f"🔎 Returning {len(results[:top_k])} results")
    return results[:top_k]