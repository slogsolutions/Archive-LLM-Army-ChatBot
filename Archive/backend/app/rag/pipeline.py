from __future__ import annotations
import re

from app.rag.ingestion.cleaner import clean_text
from app.rag.ingestion.parser import extract_metadata, ParsedDocument, ParsedPage
from app.rag.ingestion.chunker import chunk_document
from app.rag.embedding.embedder import get_embeddings
from app.rag.ingestion.indexer import index_chunks
from app.rag.vector_store.elastic_store import delete_doc_chunks


def ingest_document(doc, parsed_doc: ParsedDocument | None = None) -> int:
    """
    Full RAG ingestion pipeline.

      parse (optional) → clean → chunk → embed → delete-old → bulk-index

    Args:
        doc:        SQLAlchemy Document model instance (already committed)
        parsed_doc: optional pre-parsed document from the OCR worker.
                    When None, the pipeline reconstructs page structure
                    from doc.corrected_text or doc.ocr_text.

    Returns:
        Number of chunks indexed (0 on failure).
    """
    print(f"[PIPELINE] Ingesting doc_id={doc.id}")

    # ── 1. Build ParsedDocument if not supplied ────────────────────────────
    if parsed_doc is None:
        raw_text = (doc.corrected_text or doc.ocr_text or "").strip()
        if not raw_text:
            print(f"[PIPELINE] doc_id={doc.id}: no text available, skipping")
            return 0

        # OCR service joins pages with "\n\n"; reconstruct per-page objects
        page_texts = [t.strip() for t in re.split(r"\n{2,}", raw_text) if t.strip()]
        pages = [
            ParsedPage(page_number=i + 1, text=t)
            for i, t in enumerate(page_texts)
        ]
        parsed_doc = ParsedDocument(pages=pages, file_type=doc.file_type or "")

    # ── 2. Clean each page (preserve paragraph structure) ─────────────────
    for page in parsed_doc.pages:
        page.text = clean_text(page.text)

    parsed_doc.pages = [p for p in parsed_doc.pages if p.text.strip()]

    if not parsed_doc.pages:
        print(f"[PIPELINE] doc_id={doc.id}: no content after cleaning, skipping")
        return 0

    # ── 3. Extract document-level metadata for every chunk ────────────────
    metadata = extract_metadata(doc)

    # ── 4. Chunk (sentence-aware sliding window with overlap) ─────────────
    chunks = chunk_document(parsed_doc.pages, chunk_size=350, overlap=80)

    from app.models.document_chunks import DocumentChunk
    from app.core.database import SessionLocal

    db = SessionLocal()

    # delete old chunks (re-index case)
    db.query(DocumentChunk).filter(
    DocumentChunk.document_id == doc.id
    ).delete()

    for c in chunks:
        db.add(DocumentChunk(
        document_id=doc.id,
        chunk_text=c.text,
        page=c.page_number,
        section=metadata.get("section"),
        chunk_index=c.chunk_index,
        total_chunks=c.total_chunks,
        heading=c.heading,
        char_offset=c.char_offset,
    ))

    db.commit()
    db.close()

    if not chunks:
        print(f"[PIPELINE] doc_id={doc.id}: chunker produced no chunks")
        return 0

    print(f"[PIPELINE] doc_id={doc.id}: {len(chunks)} chunks from {len(parsed_doc.pages)} pages")

    # ── 5. Embed in batch ─────────────────────────────────────────────────
    # CHUNK DEDUPLICATION
    seen = set()
    unique_chunks = []
    
    for c in chunks:
        key = c.text.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_chunks.append(c)

    chunks = unique_chunks
    texts = [c.text for c in chunks]

    embeddings = get_embeddings(texts)

    if len(embeddings) != len(chunks):
        print(f"[PIPELINE] doc_id={doc.id}: embedding count mismatch, aborting")
        return 0

    # ── 6. Remove previously indexed chunks (handles re-ingestion) ────────
    try:
        delete_doc_chunks(doc.id)
    except Exception:
        pass

    # ── 7. Bulk-index ─────────────────────────────────────────────────────
    count = index_chunks(doc.id, chunks, embeddings, metadata)
    print(f"[PIPELINE] doc_id={doc.id}: indexed {count} chunks")
    return count
