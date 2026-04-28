
# IMPROVED VERSION 

from __future__ import annotations
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Union

load_dotenv(dotenv_path=Path(__file__).resolve().parents[4] / ".env")

from app.rag.vector_store.elastic_store import get_es, ensure_index, INDEX_NAME
from app.rag.ingestion.chunker import Chunk, ListItem

_es = None


def _get_client():
    global _es
    if _es is None:
        es = get_es()
        _es = ensure_index(es)
        
    return _es


def index_chunks(
    doc_id: int,
    chunks: List[Union[Chunk, ListItem]],
    embeddings: List[list],
    metadata: dict,
) -> int:
    """
    Bulk-index all chunks (Chunk or ListItem) for a document into Elasticsearch.

    🔥 NEW: Handles both prose chunks and list items with full metadata.

    Each document in the index carries:
      - content, embedding (for semantic search)
      - command, description, rank_in_section (for structured queries)
      - page/chunk position fields (for display)
      - metadata fields (for filtering and RBAC)

    Args:
        doc_id:     parent document ID
        chunks:     list of Chunk or ListItem objects
        embeddings: list of embedding vectors (must match len(chunks))
        metadata:   dict with doc-level fields (branch, doc_type, year, section...)

    Returns:
        Number of successfully indexed chunks.
    """
    if not chunks or not embeddings:
        return 0

    if len(chunks) != len(embeddings):
        print(f"[INDEXER] ERROR: {len(chunks)} chunks but {len(embeddings)} embeddings")
        return 0

    es = _get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Build bulk operations list: [action, doc, action, doc, ...]
    operations = []
    
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # Index metadata
        index_meta = {
            "_index": INDEX_NAME,
            "_id": f"{doc_id}_{i}"  # Unique per chunk across all docs
        }
        operations.append({"index": index_meta})
        
        # Document body
        doc_body = {
            "doc_id":           doc_id,
            "content":          "",  # Will be overwritten per type
            "embedding":        embedding,
            "is_list_item":     isinstance(chunk, ListItem),

            # Keywords: doc-level user-supplied + auto-extracted
            "keywords":         metadata.get("keywords", ""),

            # Access control & metadata
            "branch":           metadata.get("branch", ""),
            "unit_id":          metadata.get("unit_id"),
            "hq_id":            metadata.get("hq_id"),
            "doc_type":         metadata.get("doc_type", ""),
            "year":             metadata.get("year"),
            "file_name":        metadata.get("file_name", ""),
            "file_type":        metadata.get("file_type", ""),
            "uploaded_by":      metadata.get("uploaded_by"),
            "min_visible_rank": metadata.get("min_visible_rank", 6),
            "created_at":       now,
        }

        # 🔥 DISPATCH by type
        if isinstance(chunk, ListItem):
            _index_list_item(doc_body, chunk)
        else:  # Chunk
            _index_prose_chunk(doc_body, chunk)

        operations.append(doc_body)

    # Bulk index
    try:
        resp = es.bulk(body=operations, refresh=True)
        errors = [
            item for item in resp.get("items", [])
            if "error" in item.get("index", {})
        ]
        if errors:
            print(f"[INDEXER] {len(errors)} bulk errors for doc_id={doc_id}")
            for err in errors[:3]:  # Print first 3
                print(f"  {err['index']['error']}")
        
        indexed = len(chunks) - len(errors)
        print(f"[INDEXER] Indexed {indexed}/{len(chunks)} chunks for doc_id={doc_id}")
        return indexed
    except Exception as e:
        print(f"[INDEXER] Bulk index failed for doc_id={doc_id}: {e}")
        return 0


def _index_list_item(doc_body: dict, item: ListItem) -> None:
    """
    Populate doc_body for a ListItem (numbered command).
    
    Example fields:
      - command: "ls -al"
      - description: "Formatted listing with hidden files"
      - rank_in_section: 2
      - category: "file_commands"
    """
    doc_body.update({
        "content":          item.full_text,  # "ls -al Formatted listing..."
        "command":          item.command,     # "ls -al"
        "description":      item.description, # "Formatted listing with hidden files"
        "rank_in_section":  item.rank,        # 2
        "category":         item.category,    # "file_commands"
        "section":          item.section,     # "File Commands"
        "page_number":      0,               # Not applicable for list items
        "chunk_index":      0,
        "total_chunks":     1,
        "heading":          item.section,
        "char_offset":      0,
    })


def _index_prose_chunk(doc_body: dict, chunk: Chunk) -> None:
    """
    Populate doc_body for a prose Chunk (continuous text, chunked by sliding window).
    
    These chunks don't have command/description/rank because they're
    not from a structured list.
    """
    doc_body.update({
        "content":          chunk.text,
        "command":          "",            # N/A
        "description":      "",            # N/A
        "rank_in_section":  0,             # N/A
        "category":         "prose",       # Mark as prose
        "section":          "",
        "page_number":      chunk.page_number,
        "chunk_index":      chunk.chunk_index,
        "total_chunks":     chunk.total_chunks,
        "heading":          chunk.heading or "",
        "char_offset":      chunk.char_offset,
    })


def index_document(
    doc_id: int,
    parsed_chunks: List[Union[Chunk, ListItem]],
    embedder_fn,  # Function that takes list of texts, returns embeddings
    metadata: dict,
) -> int:
    """
    End-to-end indexing pipeline: chunk → embed → index.
    
    Args:
        doc_id:          Document ID
        parsed_chunks:   Output from chunker.chunk_document()
        embedder_fn:     Function(texts: List[str]) → List[List[float]]
        metadata:        Document metadata dict
    
    Returns:
        Number of indexed chunks.
    
    Example:
        from app.rag.ingestion.embedder import get_embeddings
        
        chunks = chunk_document(pages)
        texts = [c.text if isinstance(c, Chunk) else c.full_text for c in chunks]
        indexed = index_document(
            doc_id=42,
            parsed_chunks=chunks,
            embedder_fn=get_embeddings,
            metadata=extract_metadata(doc_obj)
        )
    """
    if not parsed_chunks:
        print(f"[INDEXER] No chunks to index for doc_id={doc_id}")
        return 0
    
    # Extract text from each chunk (handles both Chunk and ListItem)
    texts_to_embed = []
    for chunk in parsed_chunks:
        if isinstance(chunk, ListItem):
            texts_to_embed.append(chunk.full_text)
        else:  # Chunk
            texts_to_embed.append(chunk.text)
    
    # Generate embeddings
    print(f"[INDEXER] Generating {len(texts_to_embed)} embeddings...")
    embeddings = embedder_fn(texts_to_embed)
    
    if len(embeddings) != len(parsed_chunks):
        print(f"[INDEXER] ERROR: Got {len(embeddings)} embeddings, expected {len(parsed_chunks)}")
        return 0
    
    # Index
    return index_chunks(doc_id, parsed_chunks, embeddings, metadata)