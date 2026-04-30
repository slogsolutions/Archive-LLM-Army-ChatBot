"""
Document Ingestion Pipeline
============================
Single entry point: ingest_document(doc, parsed_doc=None)

Strategy
--------
Shared pre-processing (steps 1-4) → then picks the best chunking path:

  Path A — Parent-Child (preferred)
    Requires: markdown sections detected by md_parser
    Produces: ParentChunk (full sections) + ChildChunk (120-word sub-chunks)
    Indexed as: is_parent=True/False in ES, parent_id FK on children

  Path B — Flat chunks (fallback)
    Used when: no markdown sections found (plain-text, old OCR blobs)
    Produces: Chunk / ListItem (150-word sliding window or numbered list items)
    Indexed as: flat documents in ES (backward compatible)

Both paths save chunk text to the PostgreSQL document_chunks table for
admin review, and index embeddings into Elasticsearch.
"""
from __future__ import annotations
import os
import re
import tempfile
from typing import Union

from app.rag.ingestion.cleaner     import clean_text
from app.rag.ingestion.ocr_cleaner import apply_ocr_pipeline
from app.rag.ingestion.parser      import extract_metadata, ParsedDocument, ParsedPage, _parse_pdf
from app.rag.ingestion.chunker     import (
    chunk_document, chunk_into_parent_child,
    Chunk, ListItem, ChildChunk,
)
from app.rag.embedding.embedder          import get_embeddings
from app.rag.ingestion.indexer           import index_chunks, index_parent_child
from app.rag.vector_store.elastic_store  import delete_doc_chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_document(doc, parsed_doc: ParsedDocument | None = None) -> int:
    """
    Ingest a document: parse → clean → chunk → embed → index.

    Parameters
    ----------
    doc        : ORM Document object (must have .id, .minio_path, .ocr_text, etc.)
    parsed_doc : Pre-built ParsedDocument, or None to build it here.

    Returns
    -------
    Number of chunks/children successfully indexed into Elasticsearch.
    """
    print(f"[PIPELINE] doc_id={doc.id}  file={doc.file_name}")

    # ── 1. Acquire ParsedDocument ─────────────────────────────────────────
    if parsed_doc is None:
        parsed_doc = _acquire_parsed_doc(doc)
        if parsed_doc is None:
            return 0

    # ── 2. OCR + Text cleaning ────────────────────────────────────────────
    for page in parsed_doc.pages:
        page.text = apply_ocr_pipeline(page.text)
    for page in parsed_doc.pages:
        page.text = clean_text(page.text)

    parsed_doc.pages = [p for p in parsed_doc.pages if p.text.strip()]
    if not parsed_doc.pages:
        print(f"[PIPELINE] doc_id={doc.id}: empty after cleaning — skipping")
        return 0

    # ── 3. Metadata ───────────────────────────────────────────────────────
    metadata = extract_metadata(doc, parsed_doc)

    # ── 4a. Parent-child path (preferred) ────────────────────────────────
    # Build sections directly from ParsedDocument pages — each page IS one
    # section (heading + body + page_number) created by markdown_to_parsed_doc.
    # Do NOT re-parse parsed_doc.full_text because full_text strips headings.
    sections = [
        (parsed_doc.title or "", p.heading or "", p.text, p.page_number)
        for p in parsed_doc.pages
        if p.text.strip()
    ]
    print(f"[PIPELINE] doc_id={doc.id}: {len(sections)} sections from ParsedDocument")

    if sections:
        parents, children = chunk_into_parent_child(sections, doc_id=doc.id)
        print(f"[PIPELINE] doc_id={doc.id}: {len(parents)} parents, {len(children)} children")
        if children:
            return _ingest_parent_child(doc, parents, children, metadata)
        print(f"[PIPELINE] doc_id={doc.id}: no children produced — using flat fallback")

    # ── 4b. Flat-chunk fallback ───────────────────────────────────────────
    return _ingest_flat(doc, parsed_doc, metadata)


# ---------------------------------------------------------------------------
# Private: parent-child path
# ---------------------------------------------------------------------------

def _ingest_parent_child(doc, parents, children, metadata: dict) -> int:
    print(f"[PIPELINE] doc_id={doc.id}: parent-child path — "
          f"{len(parents)} sections, {len(children)} children")

    # Save children to Postgres for admin review
    _save_chunks_to_db(
        doc_id=doc.id,
        chunks=children,
        metadata=metadata,
        section_field=lambda c: c.heading,
    )

    # Embed children only (parents have no embedding)
    embeddings = get_embeddings([c.text for c in children])
    if not embeddings or len(embeddings) != len(children):
        print(f"[PIPELINE] doc_id={doc.id}: embedding mismatch — aborting")
        return 0

    # Delete old ES docs, bulk-index parents + children
    try:
        delete_doc_chunks(doc.id)
    except Exception as e:
        print(f"[PIPELINE] doc_id={doc.id}: ES delete warning — {e}")

    n_parents, n_children = index_parent_child(
        doc.id, parents, children, embeddings, metadata
    )
    print(f"[PIPELINE] doc_id={doc.id}: indexed {n_parents} parents + {n_children} children")
    return n_children


# ---------------------------------------------------------------------------
# Private: flat-chunk fallback
# ---------------------------------------------------------------------------

def _ingest_flat(doc, parsed_doc: ParsedDocument, metadata: dict) -> int:
    chunks: list[Union[Chunk, ListItem]] = chunk_document(
        parsed_doc.pages, chunk_size=150, overlap=30
    )
    if not chunks:
        print(f"[PIPELINE] doc_id={doc.id}: no chunks — skipping")
        return 0

    list_count  = sum(1 for c in chunks if isinstance(c, ListItem))
    prose_count = sum(1 for c in chunks if isinstance(c, Chunk))
    print(f"[PIPELINE] doc_id={doc.id}: flat path — "
          f"{list_count} list items + {prose_count} prose chunks before dedup")

    # Dedup by text
    seen: set[str] = set()
    chunks = [c for c in chunks if (k := c.text.strip().lower()) not in seen and not seen.add(k)]  # type: ignore
    print(f"[PIPELINE] doc_id={doc.id}: {len(chunks)} after dedup")

    # Save to Postgres
    _save_chunks_to_db(
        doc_id=doc.id,
        chunks=chunks,
        metadata=metadata,
        section_field=lambda c: c.section if isinstance(c, ListItem) else "",
    )

    # Embed + index
    embeddings = get_embeddings([c.text for c in chunks])
    if not embeddings or len(embeddings) != len(chunks):
        print(f"[PIPELINE] doc_id={doc.id}: embedding mismatch — aborting")
        return 0

    try:
        delete_doc_chunks(doc.id)
    except Exception as e:
        print(f"[PIPELINE] doc_id={doc.id}: ES delete warning — {e}")

    count = index_chunks(doc.id, chunks, embeddings, metadata)
    print(f"[PIPELINE] doc_id={doc.id}: indexed {count}/{len(chunks)} flat chunks")
    return count


# ---------------------------------------------------------------------------
# Private: acquire ParsedDocument
# ---------------------------------------------------------------------------

def _acquire_parsed_doc(doc) -> ParsedDocument | None:
    """
    Download from MinIO (→ md_parser cascade) or use stored OCR text.
    Returns None if nothing is available.
    """
    ocr_fallback = (doc.corrected_text or doc.ocr_text or "").strip()
    is_pdf = (
        (doc.file_type or "").lower() in ("application/pdf", "pdf")
        or (doc.file_name or "").lower().endswith(".pdf")
    )

    # Try to download original PDF and run md_parser
    if is_pdf and doc.minio_path:
        tmp = os.path.join(tempfile.gettempdir(), f"pipeline_{doc.id}_{doc.file_name}")
        try:
            from app.services.minio_service import download_file
            download_file(doc.minio_path, tmp)
            parsed = _parse_pdf(tmp, ocr_text=ocr_fallback)
            return parsed
        except Exception as e:
            print(f"[PIPELINE] doc_id={doc.id}: MinIO/parse failed ({e}) — using stored text")
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass

    # Fall back to stored OCR text
    if ocr_fallback:
        page_texts = [t.strip() for t in re.split(r"\n{2,}", ocr_fallback) if t.strip()]
        return ParsedDocument(
            pages=[ParsedPage(page_number=i + 1, text=t) for i, t in enumerate(page_texts)],
            file_type=doc.file_type or "",
        )

    print(f"[PIPELINE] doc_id={doc.id}: no PDF and no stored text — skipping")
    return None


# ---------------------------------------------------------------------------
# Private: Postgres save (shared by both paths)
# ---------------------------------------------------------------------------

def _save_chunks_to_db(doc_id: int, chunks, metadata: dict, section_field) -> None:
    """Save chunk/child texts to document_chunks table for admin review."""
    from app.models.document_chunks import DocumentChunk
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
        for c in chunks:
            db.add(DocumentChunk(
                document_id = doc_id,
                chunk_text  = c.text,
                page        = c.page_number,
                section     = metadata.get("section") or section_field(c),
                chunk_index = c.chunk_index,
                total_chunks= getattr(c, "total_chunks", 0),
                heading     = c.heading,
                char_offset = getattr(c, "char_offset", 0),
            ))
        db.commit()
        print(f"[PIPELINE] doc_id={doc_id}: saved {len(chunks)} rows to document_chunks")
    except Exception as e:
        db.rollback()
        print(f"[PIPELINE] doc_id={doc_id}: DB save failed — {e}")
        raise
    finally:
        db.close()
