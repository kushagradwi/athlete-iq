"""Original-file storage: S3/MinIO when configured, local directory otherwise."""
from __future__ import annotations

import os

from .config import settings


def _s3():
    import boto3
    s = settings()
    return boto3.client("s3", endpoint_url=s.s3_endpoint, aws_access_key_id=s.s3_access_key,
                        aws_secret_access_key=s.s3_secret_key, region_name="us-east-1")


def ensure_bucket():
    s = settings()
    if s.storage != "s3":
        os.makedirs(s.local_storage_dir, exist_ok=True)
        return
    c = _s3()
    try:
        c.head_bucket(Bucket=s.s3_bucket)
    except Exception:
        c.create_bucket(Bucket=s.s3_bucket)


def put(key: str, data: bytes) -> None:
    s = settings()
    if s.storage == "s3":
        _s3().put_object(Bucket=s.s3_bucket, Key=key, Body=data)
    else:
        path = os.path.join(s.local_storage_dir, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)


def get(key: str) -> bytes:
    s = settings()
    if s.storage == "s3":
        return _s3().get_object(Bucket=s.s3_bucket, Key=key)["Body"].read()
    with open(os.path.join(s.local_storage_dir, key), "rb") as fh:
        return fh.read()
