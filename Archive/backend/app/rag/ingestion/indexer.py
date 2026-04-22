from __future__ import annotations
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from typing import List

load_dotenv(dotenv_path=Path(__file__).resolve().parents[4] / ".env")

from app.rag.vector_store.elastic_store import get_es, ensure_index, INDEX_NAME
from app.rag.ingestion.chunker import Chunk

_es = None


def _get_client():
    global _es
    if _es is None:
        es = get_es()
        _es = ensure_index(es)
        
    return _es


def index_chunks(
    doc_id: int,
    chunks: List[Chunk],
    embeddings: List[list],
    metadata: dict,
) -> int:
    """
    Bulk-index all chunks for a document into Elasticsearch.

    Each document in the index carries:
      - content, embedding (for search)
      - page/chunk position fields (for display)
      - metadata fields (for filtering and RBAC)

    Returns the number of successfully indexed chunks.
    """
    if not chunks or not embeddings:
        return 0

    es = _get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Build bulk operations list: [action, doc, action, doc, ...]
    operations = []
    for chunk, embedding in zip(chunks, embeddings):
        # operations.append({"index": {"_index": INDEX_NAME}})
        operations.append({
        "index": {
             "_index": INDEX_NAME,
             "_id": f"{doc_id}_{chunk.chunk_index}"
    }
})
        operations.append({
            "doc_id":           doc_id,
            "content":          chunk.text,
            "embedding":        embedding,
            # chunk position
            "page_number":      chunk.page_number,
            "chunk_index":      chunk.chunk_index,
            "total_chunks":     chunk.total_chunks,
            "heading":          chunk.heading or "",
            "char_offset":      chunk.char_offset,
            # filterable document metadata
            "branch":           metadata.get("branch", ""),
            "unit_id":          metadata.get("unit_id"),
            "hq_id":            metadata.get("hq_id"),
            "doc_type":         metadata.get("doc_type", ""),
            "year":             metadata.get("year"),
            "section":          metadata.get("section", ""),
            "file_name":        metadata.get("file_name", ""),
            "file_type":        metadata.get("file_type", ""),
            # access control
            "uploaded_by":      metadata.get("uploaded_by"),
            "min_visible_rank": metadata.get("min_visible_rank", 6),
            "created_at":       now,
        })

    try:
        # resp = es.bulk(operations=operations, refresh=True)
        resp = es.bulk(body=operations, refresh=True)
        errors = [
            item for item in resp.get("items", [])
            if "error" in item.get("index", {})
        ]
        if errors:
            print(f"[INDEXER] {len(errors)} bulk errors for doc_id={doc_id}")
        indexed = len(chunks) - len(errors)
        print(f"[INDEXER] Indexed {indexed}/{len(chunks)} chunks for doc_id={doc_id}")
        return indexed
    except Exception as e:
        print(f"[INDEXER] Bulk index failed for doc_id={doc_id}: {e}")
        return 0
