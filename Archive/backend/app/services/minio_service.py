from minio import Minio
from fastapi import UploadFile
from app.core.config import (
    MINIO_ENDPOINT,
    MINIO_ACCESS_KEY,
    MINIO_SECRET_KEY,
    MINIO_BUCKET
)

# print("MINIO_ENDPOINT:", MINIO_ENDPOINT)
# print("MINIO_ACCESS_KEY:", MINIO_ACCESS_KEY)
# print("MINIO_BUCKET:", MINIO_BUCKET)



client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

try:
    if not client.bucket_exists(MINIO_BUCKET):
        print("Creating bucket:", MINIO_BUCKET)
        client.make_bucket(MINIO_BUCKET)
except Exception as e:
    print("❌ MinIO connection failed:", str(e))
    raise

# =========================
# UPLOAD FILE
# =========================

def upload_file(file: UploadFile, file_name: str):
    print("=== MINIO UPLOAD START ===")

    # Ensure bucket exists
    if not client.bucket_exists(MINIO_BUCKET):
        print("Creating bucket:", MINIO_BUCKET)
        client.make_bucket(MINIO_BUCKET)

    object_name = f"documents/{file_name}"
    print("Uploading:", object_name)

     # ✅ Get file size properly
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    print("File size:", file_size)

    try:
        client.put_object(
            bucket_name=MINIO_BUCKET,
            object_name=object_name,
            data=file.file,
            length=file_size,   # ✅ FIXED
            content_type=file.content_type
        )
    except Exception as e:
        print("❌ Upload failed:", e)
        raise

    print("✅ Upload successful")


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