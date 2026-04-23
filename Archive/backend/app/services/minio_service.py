from minio import Minio
from fastapi import UploadFile
from minio.commonconfig import CopySource

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


def move_to_deleted(file_path: str):

    # file_path example: "bucket/documents/abc.pdf"
    parts = file_path.split("/", 1)

    if len(parts) != 2:
        raise Exception("Invalid file path")

    bucket_name, object_name = parts

    deleted_path = f"deleted/{object_name}"

    # ✅ CORRECT COPY
    source = CopySource(bucket_name, object_name)

    client.copy_object(
        MINIO_BUCKET,   # destination bucket
        deleted_path,   # destination path
        source          # ✅ MUST be CopySource
    )

    # ✅ DELETE ORIGINAL
    client.remove_object(bucket_name, object_name)

    return f"{MINIO_BUCKET}/{deleted_path}"