from app.core.queue import celery_app

@celery_app.task
def process_document(doc_id):
    print(f"Processing OCR for doc {doc_id}")

    # Later:
    # - fetch file from MinIO
    # - run PaddleOCR
    # - save text in DB