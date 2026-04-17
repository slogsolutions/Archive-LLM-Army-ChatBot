from minio import Minio
from fastapi import UploadFile
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
# UPLOAD FILE
# =========================
def upload_file(file: UploadFile, file_name: str):

    # Create bucket if not exists
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    object_name = f"documents/{file_name}"

    client.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_name,
        data=file.file,
        length=-1,
        part_size=10 * 1024 * 1024,
        content_type=file.content_type
    )

    return f"{MINIO_BUCKET}/{object_name}"


# =========================
# DOWNLOAD FILE (TO LOCAL)
# =========================
def download_file(object_path: str, local_path: str):

    object_name = object_path.replace(f"{MINIO_BUCKET}/", "")

    client.fget_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_name,
        file_path=local_path
    )


# =========================
# STREAM FILE (FOR API)
# =========================
def get_file_stream(object_path: str):

    object_name = object_path.replace(f"{MINIO_BUCKET}/", "")

    return client.get_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_name
    )