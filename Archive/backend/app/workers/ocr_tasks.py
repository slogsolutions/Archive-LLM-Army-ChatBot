from app.core.queue import celery_app
from app.core.database import SessionLocal
from app.models.document import Document
from app.services.minio_service import download_file
from app.services.ocr_service import run_ocr
from app.services.search_service import index_chunk

import os

@celery_app.task
def process_document(doc_id: int):
    print(doc_id)
    print(f"[START] Processing doc_id={doc_id}")

    db = SessionLocal()

    try:
        doc = db.get(Document, doc_id)

        if not doc:
            print("[ERROR] Document not found")
            return

        # 1. STATUS
        doc.status = "processing"
        db.commit()
        print("[STEP 1] Status set to processing")

        # 2. DOWNLOAD
        local_path = f"/tmp/{doc.file_name}"
        download_file(doc.minio_path, local_path)
        print(f"[STEP 2] File downloaded to {local_path}")

        # 3. OCR
        text = run_ocr(local_path)
        print("[STEP 3] OCR completed")

        # 4. SAVE OCR
        doc.ocr_text = text
        doc.status = "processed"
        db.commit()
        print("[STEP 4] OCR text saved")

        # 5. INDEX
        index_chunk(doc.id, text)
        doc.status = "indexed"
        db.commit()
        print("[STEP 5] Indexed in Elasticsearch")

        # CLEANUP
        os.remove(local_path)
        print("[CLEANUP] Temp file removed")

        print(f"[DONE] doc_id={doc_id}")

    except Exception as e:
        print("❌ OCR ERROR:", str(e))

    finally:
        db.close()