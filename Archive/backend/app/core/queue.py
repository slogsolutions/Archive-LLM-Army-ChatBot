import os
from celery import Celery
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "worker",
    broker=_redis_url,
    backend=_redis_url,
)

try:
    from app.rag.hw_config import WORKER_CONCURRENCY
except Exception:
    WORKER_CONCURRENCY = 1

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # never pre-fetch more than 1 task per worker
    worker_concurrency=WORKER_CONCURRENCY,
)

celery_app.autodiscover_tasks(["app.workers"])
import app.workers.ocr_tasks