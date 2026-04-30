"""
Celery Workers — all heavy processing off the main FastAPI event loop.

Tasks
-----
process_document(doc_id)      Download → parse → RAG ingest.
index_corrected_text(doc_id)  Re-ingest edited text without OCR.
run_rag_query(...)            Full RAG pipeline (retrieve → LLM → log).

Start worker:
  celery -A app.core.queue:celery_app worker --loglevel=info --concurrency=1
"""
from __future__ import annotations

import os
import time
import traceback
from typing import Any

from app.core.queue    import celery_app
from app.core.database import SessionLocal
from app.models.document import Document

_OCR_EXTS    = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
_DIRECT_EXTS = {".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".ppt", ".txt", ".md"}


def _ext(fn: str) -> str:
    return os.path.splitext(fn)[1].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Task 1: Full document ingestion (download → OCR/parse → RAG ingest)
# ─────────────────────────────────────────────────────────────────────────────

def _check_ram_guard() -> bool:
    """
    Return True if RAM usage is below the configured threshold.
    If False, the task should be re-queued rather than run now.
    """
    try:
        from app.rag.hw_config import WORKER_MAX_RAM_MB
        if WORKER_MAX_RAM_MB <= 0:
            return True
        import psutil, os
        proc = psutil.Process(os.getpid())
        rss_mb = proc.memory_info().rss / (1024 * 1024)
        if rss_mb > WORKER_MAX_RAM_MB:
            print(f"[WORKER] RAM guard: {rss_mb:.0f} MB > {WORKER_MAX_RAM_MB} MB — deferring task")
            return False
    except ImportError:
        pass  # psutil not installed — skip guard
    except Exception as e:
        print(f"[WORKER] RAM check error: {e}")
    return True


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="workers.process_document",
)
def process_document(self, doc_id: int) -> dict:
    from app.rag.hw_config import WORKER_INTER_DOC_DELAY_S
    print(f"[WORKER] process_document doc_id={doc_id}")

    # RAM guard: defer if too much memory in use
    if not _check_ram_guard():
        raise self.retry(countdown=30)

    # Inter-document delay: gives GPU/RAM time to recover from previous task
    if WORKER_INTER_DOC_DELAY_S > 0:
        print(f"[WORKER] Inter-doc delay {WORKER_INTER_DOC_DELAY_S}s…")
        time.sleep(WORKER_INTER_DOC_DELAY_S)
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return {"status": "error", "reason": "not_found"}

        doc.status = "processing"
        db.commit()

        # Download from MinIO
        from app.services.minio_service import download_file
        import tempfile
        local = os.path.join(tempfile.gettempdir(), f"w{doc_id}_{doc.file_name}")
        download_file(doc.minio_path, local)

        ext = _ext(doc.file_name)
        from app.rag.ingestion.parser import ParsedDocument
        parsed_doc: ParsedDocument | None = None

        if ext in _OCR_EXTS:
            # Strategy cascade: Marker → Docling → PyMuPDF → PaddleOCR
            ocr_text = ""
            if ext != ".pdf":
                try:
                    from paddleocr import PaddleOCR
                    p = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
                    r = p.ocr(local, cls=True)
                    ocr_text = "\n".join(
                        ln[1][0] for pg in (r or []) for ln in (pg or []) if ln
                    )
                except Exception as e:
                    print(f"[WORKER] PaddleOCR err: {e}")

            from app.rag.ingestion.md_parser import convert_to_markdown
            from app.rag.ingestion.parser   import markdown_to_parsed_doc
            md = convert_to_markdown(file_path=local, ocr_text=ocr_text)
            print(f"[WORKER] MD: method={md.method} quality={md.quality:.2f} chars={len(md.markdown)}")

            if md.markdown.strip():
                doc.ocr_text      = md.markdown
                doc.corrected_text = md.markdown
                parsed_doc        = markdown_to_parsed_doc(md.markdown, md.method)

        elif ext in _DIRECT_EXTS:
            from app.rag.ingestion.parser import parse_document
            parsed_doc = parse_document(local)
            if parsed_doc and parsed_doc.full_text:
                doc.ocr_text = parsed_doc.full_text

        try:
            os.remove(local)
        except Exception:
            pass

        if not parsed_doc or not parsed_doc.pages:
            doc.status = "error"
            db.commit()
            return {"status": "error", "reason": "no_content"}

        db.commit()

        from app.rag.pipeline import ingest_document
        count = ingest_document(doc, parsed_doc=parsed_doc)
        doc.status = "indexed" if count > 0 else "processed"
        db.commit()

        print(f"[WORKER] done doc_id={doc_id} chunks={count}")
        return {"status": "ok", "doc_id": doc_id, "chunks": count}

    except Exception as e:
        print(f"[WORKER] ERROR doc_id={doc_id}: {e}\n{traceback.format_exc()}")
        try:
            doc.status = "error"
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Task 2: Re-index corrected text (no download/OCR)
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
    name="workers.index_corrected_text",
)
def index_corrected_text(self, doc_id: int) -> dict:
    print(f"[WORKER] index_corrected_text doc_id={doc_id}")
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return {"status": "error", "reason": "not_found"}

        if not (doc.corrected_text or doc.ocr_text):
            doc.status = "error"
            db.commit()
            return {"status": "error", "reason": "no_text"}

        from app.rag.pipeline import ingest_document
        count = ingest_document(doc)
        doc.status = "indexed" if count > 0 else "reviewed"
        db.commit()
        return {"status": "ok", "doc_id": doc_id, "chunks": count}
    except Exception as e:
        print(f"[WORKER] index_corrected_text ERROR: {e}")
        try:
            doc.status = "error"
            db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Task 3: Async RAG query — returns JSON result stored in Redis
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="workers.run_rag_query",
    time_limit=900,        # 15 min hard limit
    soft_time_limit=840,
)
def run_rag_query(
    self,
    query:      str,
    filters:    dict | None,
    user_id:    int | None,
    session_id: str | None,
    model:      str = "llama3:latest",
    top_k:      int = 5,
) -> dict[str, Any]:
    """
    Full RAG pipeline in a worker.  Result stored in Redis/Celery backend.
    Poll via GET /chat/result/{task_id}.

    WHY: Ollama on CPU = 100–500 s.  Running on the FastAPI event loop
    blocks all concurrent requests.  Worker isolates this cost.
    """
    from app.rag.llm.qa_pipeline import ask, QAResponse
    from app.models.user import User

    t0 = time.time()
    db = SessionLocal()
    try:
        user = db.get(User, user_id) if user_id else None

        response: QAResponse = ask(
            query=query,
            filters=filters,
            top_k=top_k,
            user=user,
            model=model,
            stream=False,
            session_id=session_id,
            run_faithfulness_check=True,
            enable_agent=False,
        )

        return {
            "status":           "ok",
            "answer":           response.answer,
            "query":            response.query,
            "sources":          response.sources,
            "results_count":    response.results_count,
            "retrieval_scores": response.retrieval_scores,
            "model":            response.model,
            "intent":           response.intent,
            "faithfulness":     response.faithfulness,
            "confidence":       getattr(response, "confidence", None),
            "was_rejected":     getattr(response, "was_rejected", False),
            "latency_s":        round(time.time() - t0, 2),
            "error":            response.error,
        }
    except Exception as e:
        return {
            "status": "error", "answer": "", "query": query,
            "sources": [], "latency_s": round(time.time() - t0, 2),
            "error": str(e),
        }
    finally:
        db.close()
