from minio import Minio
from fastapi import UploadFile

from datetime import datetime
import os

from app.core.config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_BUCKET
)

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)


# =========================
# UPLOAD FILE (UPDATED)
# =========================

def upload_file(file: UploadFile, file_name: str, branch: str, document_type: str):
    print("=== MINIO UPLOAD START ===")

    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    # ✅ sanitize input
    branch = branch.strip().replace(" ", "-")
    document_type = document_type.strip().replace(" ", "-")

    # ✅ structured path
    object_name = f"documents/{branch}/{document_type}/{file_name}"

    print("Uploading:", object_name)

    # file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    client.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_name,
        data=file.file,
        length=file_size,
        content_type=file.content_type
    )

    print("✅ Upload successful")

    return f"{MINIO_BUCKET}/{object_name}"


# =========================
# DOWNLOAD FILE
# =========================
def download_file(object_path: str, local_path: str):
    object_name = object_path.replace(f"{MINIO_BUCKET}/", "")

    client.fget_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_name,
        file_path=local_path
    )


# =========================
# STREAM FILE
# =========================
def get_file_stream(object_path: str):

    object_name = object_path.replace(f"{MINIO_BUCKET}/", "")

    return client.get_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_name
    )



# =========================
# DELETE FILE (MOVE TO DELETED FODLER inside minio)
# =========================

def move_to_deleted(old_path: str) -> str:
    """
    Move file to deleted/ folder instead of permanent delete
    """
    filename = old_path.split("/")[-1]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    new_path = f"deleted/{timestamp}_{filename}"

    # Copy file to deleted folder
    client.copy_object(
        BUCKET,
        new_path,
        f"{BUCKET}/{old_path}"
    )

    # Remove original file
    client.remove_object(BUCKET, old_path)

    return new_path