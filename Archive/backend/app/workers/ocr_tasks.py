from app.core.queue import celery_app
from app.core.database import SessionLocal
from app.models.document import Document
from app.services.minio_service import download_file
from app.services.ocr_service import run_ocr_on_pdf
from app.rag.pipeline import ingest_document

import os
import cv2


@celery_app.task
def process_document(doc_id: int):

    print(f"[START] Processing doc_id={doc_id}")

    db = SessionLocal()

    try:
        doc = db.get(Document, doc_id)

        if not doc:
            print("[ERROR] Document not found")
            return

        # =========================
        # 1. STATUS
        # =========================
        doc.status = "processing"
        db.commit()

        # =========================
        # 2. DOWNLOAD
        # =========================
        local_path = f"/tmp/{doc.file_name}"
        download_file(doc.minio_path, local_path)

        # =========================
        # 3. OCR (FIXED)
        # =========================
        # img = cv2.imread(local_path)

        # if img is None:
        #     print("❌ Failed to read image")
        #     return

        # text = run_ocr_on_image(img)
        text = run_ocr_on_pdf(local_path)

        print("TEXT LENGTH:", len(text))

        if not text:
            print("❌ OCR returned empty text")
            return

        # =========================
        # 4. SAVE OCR
        # =========================
        doc.ocr_text = text
        doc.status = "processed"
        db.commit()

        # =========================
        # 5. RAG INGESTION
        # =========================
        ingest_document(doc)

        doc.status = "indexed"
        db.commit()

        # =========================
        # CLEANUP
        # =========================
        os.remove(local_path)

        print(f"[DONE] doc_id={doc_id}")

    except Exception as e:
        print("❌ ERROR:", str(e))

    finally:
        db.close()