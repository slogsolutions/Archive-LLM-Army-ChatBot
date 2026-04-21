from __future__ import annotations
import os
import traceback

from app.core.queue import celery_app
from app.core.database import SessionLocal
from app.models.document import Document
from app.services.minio_service import download_file
from app.rag.pipeline import ingest_document
from app.rag.ingestion.parser import ParsedDocument, ParsedPage

# File extensions that require OCR (cannot be parsed as structured text)
_OCR_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
# File extensions parsed directly without OCR
_DIRECT_EXTENSIONS = {".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".ppt", ".txt", ".text", ".md"}


def _ext(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


@celery_app.task
def process_document(doc_id: int):
    """
    Celery task: download → parse/OCR → save text → RAG ingest.

    Routing:
      - PDF / images  → PaddleOCR → text → pipeline
      - DOCX/XLSX/CSV/PPTX/TXT → direct parser → pipeline
      - Unknown ext   → attempt direct parse, fall back to pipeline with empty text
    """
    print(f"[WORKER] Starting doc_id={doc_id}")
    db = SessionLocal()

    try:
        doc = db.get(Document, doc_id)
        if not doc:
            print(f"[WORKER] doc_id={doc_id} not found")
            return

        doc.status = "processing"
        db.commit()

        # ── Download from MinIO ────────────────────────────────────────────
        local_path = f"/tmp/{doc.file_name}"
        download_file(doc.minio_path, local_path)

        ext = _ext(doc.file_name)
        parsed_doc: ParsedDocument | None = None

        # ── Route by file type ─────────────────────────────────────────────
        if ext in _OCR_EXTENSIONS:
            # Scanned PDF or image: run OCR first
            if ext == ".pdf":
                from app.services.ocr_service import run_ocr_on_pdf
                ocr_text = run_ocr_on_pdf(local_path)
            else:
                from app.services.ocr_service import run_ocr_on_image_file
                ocr_text = run_ocr_on_image_file(local_path)

            if not ocr_text.strip():
                print(f"[WORKER] OCR returned empty text for doc_id={doc_id}")
                doc.status = "error"
                db.commit()
                return

            doc.ocr_text = ocr_text
            doc.status = "processed"
            db.commit()

            # Build page-aware ParsedDocument from OCR text
            page_texts = [t.strip() for t in ocr_text.split("\n\n") if t.strip()]
            if not page_texts:
                page_texts = [ocr_text.strip()]
            pages = [ParsedPage(page_number=i + 1, text=t) for i, t in enumerate(page_texts)]
            parsed_doc = ParsedDocument(pages=pages, file_type=ext.lstrip("."))

        elif ext in _DIRECT_EXTENSIONS:
            # Structured document: parse directly
            from app.rag.ingestion.parser import parse_document
            parsed_doc = parse_document(local_path)

            if not parsed_doc.pages:
                print(f"[WORKER] No content extracted from {ext} for doc_id={doc_id}")
                doc.status = "error"
                db.commit()
                return

            doc.ocr_text = parsed_doc.full_text
            doc.status = "processed"
            db.commit()

        else:
            # Unknown format: attempt direct parse, log and continue
            print(f"[WORKER] Unknown extension '{ext}' for doc_id={doc_id}, attempting direct parse")
            from app.rag.ingestion.parser import parse_document
            parsed_doc = parse_document(local_path)
            doc.ocr_text = parsed_doc.full_text or ""
            doc.status = "processed"
            db.commit()

        # ── RAG ingestion ──────────────────────────────────────────────────
        count = ingest_document(doc, parsed_doc)
        doc.status = "indexed" if count > 0 else "processed"
        db.commit()

        print(f"[WORKER] Done doc_id={doc_id}, chunks={count}")

    except Exception as e:
        print(f"[WORKER] Error processing doc_id={doc_id}: {e}")
        traceback.print_exc()
        try:
            doc.status = "error"
            db.commit()
        except Exception:
            pass

    finally:
        # Clean up temp file
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
        except Exception:
            pass
        db.close()
