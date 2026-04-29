"""MinIO store — Bronze/Silver JSON files backed by S3-compatible object storage."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_BUCKET_BRONZE = "bronze"
_BUCKET_SILVER = "silver"


class MinIOStore:
    """Upload/download Bronze and Silver JSON records to MinIO (S3-compatible)."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self._endpoint = endpoint_url or os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
        self._access = access_key or os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        self._secret = secret_key or os.environ.get("MINIO_SECRET_KEY", "minioadmin")
        self._client = None

    def _get_client(self):
        if self._client is None:
            import socket
            from urllib.parse import urlparse

            parsed = urlparse(self._endpoint)
            host = parsed.hostname or "localhost"
            port = parsed.port or 80
            try:
                with socket.create_connection((host, port), timeout=1):
                    pass
            except OSError as exc:
                raise RuntimeError(f"MinIO unreachable at {self._endpoint}") from exc

            import boto3
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access,
                aws_secret_access_key=self._secret,
                region_name="us-east-1",
            )
            for bucket in (_BUCKET_BRONZE, _BUCKET_SILVER):
                try:
                    self._client.head_bucket(Bucket=bucket)
                except Exception:
                    try:
                        self._client.create_bucket(Bucket=bucket)
                        log.info("MinIOStore: created bucket %s", bucket)
                    except Exception as e:
                        log.warning("MinIOStore: could not create bucket %s: %s", bucket, e)
        return self._client

    def upload_bronze(self, entity_id: str, source: str, sha: str, data: dict[str, Any]) -> str:
        """Upload raw Bronze record. Returns object key."""
        key = f"{entity_id}/{source}/{sha}.json"
        body = json.dumps(data, ensure_ascii=False).encode()
        self._get_client().put_object(
            Bucket=_BUCKET_BRONZE,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return key

    def upload_silver(self, entity_id: str, source: str, sha: str, record: dict[str, Any]) -> str:
        """Upload normalized Silver record. Returns object key."""
        key = f"{entity_id}/{source}/{sha}.json"
        body = json.dumps(record, ensure_ascii=False, indent=2).encode()
        self._get_client().put_object(
            Bucket=_BUCKET_SILVER,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return key

    def download_silver(self, key: str) -> dict[str, Any] | None:
        """Download a Silver record by key."""
        try:
            resp = self._get_client().get_object(Bucket=_BUCKET_SILVER, Key=key)
            return json.loads(resp["Body"].read())
        except Exception as e:
            log.warning("MinIOStore: download failed for %s: %s", key, e)
            return None

    def list_silver(self, entity_id: str) -> list[str]:
        """List all Silver object keys for an entity."""
        try:
            paginator = self._get_client().get_paginator("list_objects_v2")
            keys = []
            for page in paginator.paginate(Bucket=_BUCKET_SILVER, Prefix=f"{entity_id}/"):
                keys.extend(obj["Key"] for obj in page.get("Contents", []))
            return keys
        except Exception as e:
            log.warning("MinIOStore: list failed for %s: %s", entity_id, e)
            return []
