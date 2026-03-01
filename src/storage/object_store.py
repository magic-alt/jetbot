"""S3-compatible object storage for PDFs and rendered page images.

Supports AWS S3, MinIO, and any S3-compatible endpoint.
Falls back to local filesystem when ``boto3`` is not installed or
credentials are not configured.

Usage::

    store = ObjectStore()
    url = store.put("docs/abc123/raw.pdf", pdf_bytes)
    data = store.get("docs/abc123/raw.pdf")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

_logger = get_logger(__name__)

try:
    import boto3  # type: ignore[import-untyped]
    from botocore.exceptions import ClientError  # type: ignore[import-untyped]

    BOTO3_AVAILABLE = True
except Exception:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment]
    BOTO3_AVAILABLE = False


class ObjectStore:
    """Unified interface for object storage (S3 or local filesystem)."""

    def __init__(
        self,
        endpoint: str | None = None,
        bucket: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        local_dir: str | None = None,
    ) -> None:
        self._bucket = bucket or os.getenv("S3_BUCKET", "jetbot-pdfs")
        self._local_dir = Path(local_dir or os.getenv("DATA_DIR") or "data").resolve()
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self._client: Any = None

        _endpoint = endpoint or os.getenv("S3_ENDPOINT", "")
        _access = access_key or os.getenv("S3_ACCESS_KEY", "")
        _secret = secret_key or os.getenv("S3_SECRET_KEY", "")

        if BOTO3_AVAILABLE and _endpoint and _access and _secret:
            try:
                self._client = boto3.client(
                    "s3",
                    endpoint_url=_endpoint,
                    aws_access_key_id=_access,
                    aws_secret_access_key=_secret,
                )
                # Ensure bucket exists
                try:
                    self._client.head_bucket(Bucket=self._bucket)
                except ClientError:
                    self._client.create_bucket(Bucket=self._bucket)
                _logger.info("object_store_s3", extra={"endpoint": _endpoint, "bucket": self._bucket})
            except Exception as exc:
                _logger.warning("object_store_s3_fallback", extra={"error": str(exc)})
                self._client = None

    @property
    def is_s3(self) -> bool:
        return self._client is not None

    def put(self, key: str, data: bytes) -> str:
        """Upload *data* under *key*.  Returns the storage path/URL."""
        if self._client is not None:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
            return f"s3://{self._bucket}/{key}"

        local_path = self._local_dir / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return str(local_path)

    def get(self, key: str) -> bytes | None:
        """Download the object at *key*.  Returns ``None`` if not found."""
        if self._client is not None:
            try:
                response = self._client.get_object(Bucket=self._bucket, Key=key)
                return response["Body"].read()
            except ClientError:
                return None

        local_path = self._local_dir / key
        if local_path.exists():
            return local_path.read_bytes()
        return None

    def delete(self, key: str) -> bool:
        """Delete the object at *key*.  Returns True on success."""
        if self._client is not None:
            try:
                self._client.delete_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError:
                return False

        local_path = self._local_dir / key
        if local_path.exists():
            local_path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check whether *key* exists in the store."""
        if self._client is not None:
            try:
                self._client.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError:
                return False

        return (self._local_dir / key).exists()
