from app.core.queue import celery_app
from app.core.database import SessionLocal
from app.models.document import Document
from app.services.minio_service import download_file
from app.services.ocr_service import run_ocr
from app.services.search_service import index_document
import os


@celery_app.task
def process_document(doc_id: int):

    db = SessionLocal()

    try:
        doc = db.get(Document, doc_id)

        if not doc:
            return

        # =========================
        # 1. UPDATE STATUS
        # =========================
        doc.status = "processing"
        db.commit()

        # =========================
        # 2. DOWNLOAD FILE
        # =========================
        local_path = f"/tmp/{doc.file_name}"

        download_file(doc.minio_path, local_path)

        # =========================
        # 3. RUN OCR
        # =========================
        text = run_ocr(local_path)

        # =========================
        # 4. SAVE OCR TEXT
        # =========================
        doc.ocr_text = text
        doc.status = "processed"
        db.commit()

        # =========================
        # 5. INDEX IN ELASTIC
        # =========================
        index_document(doc.id, text)

        doc.status = "indexed"
        db.commit()

        # =========================
        # CLEANUP
        # =========================
        os.remove(local_path)

    except Exception as e:
        print("OCR ERROR:", str(e))

    finally:
        db.close()