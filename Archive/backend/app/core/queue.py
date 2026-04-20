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


celery_app.autodiscover_tasks(["app.workers"])
import app.workers.ocr_tasks