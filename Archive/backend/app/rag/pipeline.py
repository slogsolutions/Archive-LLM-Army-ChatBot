from __future__ import annotations
import re

from app.rag.ingestion.cleaner import clean_text
from app.rag.ingestion.ocr_cleaner import apply_ocr_pipeline
from app.rag.ingestion.parser import extract_metadata, ParsedDocument, ParsedPage
from app.rag.ingestion.chunker import chunk_document, Chunk, ListItem
from app.rag.embedding.embedder import get_embeddings
from app.rag.ingestion.indexer import index_chunks
from app.rag.vector_store.elastic_store import delete_doc_chunks

from typing import Union


def ingest_document(doc, parsed_doc: ParsedDocument | None = None) -> int:
    """
    Full ingestion pipeline for a single document.

    Steps
    -----
    1.  Build ParsedDocument from raw text (if not already parsed)
    2.  OCR cleaning  — recover list structure, fix artifacts
    3.  Text cleaning — normalize spacing, preserve list lines
    4.  Extract metadata
    5.  Chunk         — returns List[Chunk | ListItem]
    6.  Dedup         — by .text (works for both types now)
    7.  Save chunks to Postgres DB
    8.  Embed         — uses .text (works for both types now)
    9.  Delete old ES chunks
    10. Index into Elasticsearch

    Returns
    -------
    Number of chunks successfully indexed into ES.
    """
    print(f"[PIPELINE] Ingesting doc_id={doc.id}")

    # ─────────────────────────────────────────────────────────────────────
    # 1. BUILD PARSED DOC
    # Strategy:
    #   a) If the original PDF is in MinIO → download to /tmp → run the
    #      multi-strategy Markdown pipeline (Marker → Docling → PyMuPDF)
    #   b) Otherwise fall back to the stored ocr_text / corrected_text
    # ─────────────────────────────────────────────────────────────────────
    if parsed_doc is None:
        local_pdf_path: str | None = None
        ocr_text_fallback = (doc.corrected_text or doc.ocr_text or "").strip()
        is_pdf = (doc.file_type or "").lower() in (
            "application/pdf", "pdf"
        ) or (doc.file_name or "").lower().endswith(".pdf")

        if is_pdf and doc.minio_path:
            try:
                from app.services.minio_service import download_file
                import tempfile, os
                tmp_dir  = tempfile.gettempdir()
                tmp_path = os.path.join(tmp_dir, f"pipeline_{doc.id}_{doc.file_name}")
                download_file(doc.minio_path, tmp_path)
                local_pdf_path = tmp_path
                print(f"[PIPELINE] Downloaded PDF to {tmp_path}")
            except Exception as dl_err:
                print(f"[PIPELINE] MinIO download failed ({dl_err}) — will use stored text")

        if local_pdf_path:
            from app.rag.ingestion.parser import _parse_pdf
            parsed_doc = _parse_pdf(local_pdf_path, ocr_text=ocr_text_fallback)
            # Clean up temp file
            try:
                import os
                os.remove(local_pdf_path)
            except Exception:
                pass
        elif ocr_text_fallback:
            # Plain-text fallback: split on blank lines → pages
            page_texts = [t.strip() for t in re.split(r"\n{2,}", ocr_text_fallback) if t.strip()]
            parsed_doc = ParsedDocument(
                pages=[ParsedPage(page_number=i + 1, text=t) for i, t in enumerate(page_texts)],
                file_type=doc.file_type or "",
            )
        else:
            print(f"[PIPELINE] doc_id={doc.id}: no PDF and no stored text — skipping")
            return 0

    # ─────────────────────────────────────────────────────────────────────
    # 2. OCR CLEANING  (recover list structure BEFORE generic cleaning)
    # ─────────────────────────────────────────────────────────────────────
    #
    #   apply_ocr_pipeline() does two things:
    #     a) fix artifacts (broken hyphens, missing hyphens in "ls al" → "ls -al")
    #     b) recover_list_structure() — restores "1 cmd" → "1. cmd"
    #
    #   This MUST run before clean_text(), because clean_text() needs the
    #   dots to be present to correctly identify and preserve list lines.
    #
    for page in parsed_doc.pages:
        page.text = apply_ocr_pipeline(page.text)

    # ─────────────────────────────────────────────────────────────────────
    # 3. GENERIC TEXT CLEANING
    # ─────────────────────────────────────────────────────────────────────
    for page in parsed_doc.pages:
        page.text = clean_text(page.text)

    # Drop pages that are empty after cleaning
    parsed_doc.pages = [p for p in parsed_doc.pages if p.text.strip()]

    if not parsed_doc.pages:
        print(f"[PIPELINE] doc_id={doc.id}: no content after cleaning — skipping")
        return 0

    # ─────────────────────────────────────────────────────────────────────
    # 4. METADATA
    # ─────────────────────────────────────────────────────────────────────
    metadata = extract_metadata(doc, parsed_doc)

    # ─────────────────────────────────────────────────────────────────────
    # 5. CHUNK
    # ─────────────────────────────────────────────────────────────────────
    chunks: list[Union[Chunk, ListItem]] = chunk_document(
        parsed_doc.pages, chunk_size=150, overlap=30
    )

    if not chunks:
        print(f"[PIPELINE] doc_id={doc.id}: no chunks generated — skipping")
        return 0

    print(f"[PIPELINE] doc_id={doc.id}: {len(chunks)} chunks before dedup "
          f"({sum(1 for c in chunks if isinstance(c, ListItem))} list items, "
          f"{sum(1 for c in chunks if isinstance(c, Chunk))} prose chunks)")

    # ─────────────────────────────────────────────────────────────────────
    # 6. DEDUP
    #
    #   FIX: old code used c.text which crashed on ListItem (no .text attr).
    #   Both types now expose .text (ListItem.text is a property → full_text).
    # ─────────────────────────────────────────────────────────────────────
    seen: set[str] = set()
    unique_chunks: list[Union[Chunk, ListItem]] = []

    for c in chunks:
        key = c.text.strip().lower()       # ← works for Chunk AND ListItem
        if key not in seen:
            seen.add(key)
            unique_chunks.append(c)

    chunks = unique_chunks
    print(f"[PIPELINE] doc_id={doc.id}: {len(chunks)} chunks after dedup")

    # ─────────────────────────────────────────────────────────────────────
    # 7. SAVE TO DB
    #
    #   FIX: old code accessed c.page_number, c.chunk_index, etc. on ListItem
    #   which had none of those attrs.  Now ListItem has them (set in chunker).
    # ─────────────────────────────────────────────────────────────────────
    from app.models.document_chunks import DocumentChunk
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc.id
        ).delete()

        for c in chunks:
            db.add(DocumentChunk(
                document_id=doc.id,
                chunk_text=c.text,                      # ← .text on both types
                page=c.page_number,                     # ← on both types
                section=metadata.get("section") or (c.section if isinstance(c, ListItem) else ""),
                chunk_index=c.chunk_index,              # ← on both types
                total_chunks=c.total_chunks,            # ← on both types
                heading=c.heading,                      # ← on both types
                char_offset=c.char_offset,              # ← on both types
            ))

        db.commit()
        print(f"[PIPELINE] doc_id={doc.id}: saved {len(chunks)} chunks to DB")
    except Exception as e:
        db.rollback()
        print(f"[PIPELINE] doc_id={doc.id}: DB save failed — {e}")
        raise
    finally:
        db.close()

    # ─────────────────────────────────────────────────────────────────────
    # 8. EMBEDDING
    #
    #   FIX: old code used [c.text for c in chunks] which failed on ListItem.
    #   Now c.text works uniformly.
    #
    #   FIX: embedder.py returned `embeddings.tolist(),` (trailing comma
    #   made it a tuple). Fixed in embedder.py — returns a plain list now.
    # ─────────────────────────────────────────────────────────────────────
    texts = [c.text for c in chunks]           # ← works for both types

    print(f"[PIPELINE] doc_id={doc.id}: embedding {len(texts)} chunks…")
    embeddings = get_embeddings(texts)

    if not embeddings or len(embeddings) != len(chunks):
        print(f"[PIPELINE] doc_id={doc.id}: embedding count mismatch "
              f"(got {len(embeddings)}, expected {len(chunks)}) — skipping")
        return 0

    if len(embeddings[0]) != 768:
        raise ValueError(
            f"[PIPELINE] Embedding dimension mismatch: "
            f"got {len(embeddings[0])}, expected 768"
        )

    # ─────────────────────────────────────────────────────────────────────
    # 9. DELETE OLD ES CHUNKS
    # ─────────────────────────────────────────────────────────────────────
    try:
        delete_doc_chunks(doc.id)
    except Exception as e:
        print(f"[PIPELINE] doc_id={doc.id}: ES delete warning — {e}")

    # ─────────────────────────────────────────────────────────────────────
    # 10. INDEX INTO ELASTICSEARCH
    # ─────────────────────────────────────────────────────────────────────
    count = index_chunks(doc.id, chunks, embeddings, metadata)
    print(f"[PIPELINE] doc_id={doc.id}: indexed {count}/{len(chunks)} chunks ✅")

    return count