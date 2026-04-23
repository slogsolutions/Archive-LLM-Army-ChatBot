from __future__ import annotations
import re

from app.rag.ingestion.cleaner import clean_text
from app.rag.ingestion.parser import extract_metadata, ParsedDocument, ParsedPage
from app.rag.ingestion.chunker import chunk_document
from app.rag.embedding.embedder import get_embeddings
from app.rag.ingestion.indexer import index_chunks
from app.rag.vector_store.elastic_store import delete_doc_chunks


def ingest_document(doc, parsed_doc: ParsedDocument | None = None) -> int:

    print(f"[PIPELINE] Ingesting doc_id={doc.id}")

    # ─────────────────────────────
    # 1. BUILD PARSED DOC
    # ─────────────────────────────
    if parsed_doc is None:
        raw_text = (doc.corrected_text or doc.ocr_text or "").strip()

        if not raw_text:
            print(f"[PIPELINE] doc_id={doc.id}: no text available")
            return 0

        page_texts = [t.strip() for t in re.split(r"\n{2,}", raw_text) if t.strip()]

        parsed_doc = ParsedDocument(
            pages=[
                ParsedPage(page_number=i + 1, text=t)
                for i, t in enumerate(page_texts)
            ],
            file_type=doc.file_type or ""
        )

    # ─────────────────────────────
    # 2. CLEAN
    # ─────────────────────────────
    for page in parsed_doc.pages:
        page.text = clean_text(page.text)

    parsed_doc.pages = [p for p in parsed_doc.pages if p.text.strip()]

    if not parsed_doc.pages:
        print(f"[PIPELINE] doc_id={doc.id}: no content after cleaning")
        return 0

    # ─────────────────────────────
    # 3. METADATA
    # ─────────────────────────────
    metadata = extract_metadata(doc)

    # ─────────────────────────────
    # 4. CHUNK
    # ─────────────────────────────
    chunks = chunk_document(parsed_doc.pages, chunk_size=350, overlap=80)

    if not chunks:
        print(f"[PIPELINE] doc_id={doc.id}: no chunks generated")
        return 0

    print(f"[PIPELINE] doc_id={doc.id}: {len(chunks)} chunks before dedup")

    # ─────────────────────────────
    # 5. DEDUP 
    # ─────────────────────────────
    seen = set()
    unique_chunks = []

    for c in chunks:
        key = c.text.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_chunks.append(c)

    chunks = unique_chunks

    print(f"[PIPELINE] doc_id={doc.id}: {len(chunks)} chunks after dedup")

    # ─────────────────────────────
    # 6. SAVE TO DB (SAFE)
    # ─────────────────────────────
    from app.models.document_chunks import DocumentChunk
    from app.core.database import SessionLocal

    db = SessionLocal()

    try:
        # delete old chunks
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

    finally:
        db.close()

    # ─────────────────────────────
    # 7. EMBEDDING
    # ─────────────────────────────
    texts = [c.text for c in chunks]

    embeddings = get_embeddings(texts)

    if not embeddings or len(embeddings) != len(chunks):
        print(f"[PIPELINE] doc_id={doc.id}: embedding mismatch")
        return 0

    # 🔥 dimension check (important)
    if len(embeddings[0]) != 768:
        raise ValueError("Embedding dimension mismatch (expected 768)")

    # ─────────────────────────────
    # 8. DELETE OLD ES INDEX
    # ─────────────────────────────
    try:
        delete_doc_chunks(doc.id)
    except Exception as e:
        print(f"[PIPELINE] ES delete warning: {e}")

    # ─────────────────────────────
    # 9. INDEX
    # ─────────────────────────────
    count = index_chunks(doc.id, chunks, embeddings, metadata)

    print(f"[PIPELINE] doc_id={doc.id}: indexed {count} chunks")

    return count