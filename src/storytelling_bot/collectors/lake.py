"""Shared MinIO upload helpers — best-effort, silent on unavailability."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

_UNSET = object()
_minio = _UNSET


def _get_minio():
    global _minio
    if _minio is _UNSET:
        try:
            from ..storage.minio_store import MinIOStore
            store = MinIOStore()
            store._get_client()
            _minio = store
            log.info("lake: MinIO connected at %s", store._endpoint)
        except Exception as e:
            log.debug("lake: MinIO unavailable (%s) — uploads skipped", e)
            _minio = None
    return _minio


def upload_bronze(entity_id: str, source: str, sha: str, raw: dict[str, Any]) -> None:
    minio = _get_minio()
    if minio is None:
        return
    try:
        minio.upload_bronze(entity_id, source, sha, raw)
    except Exception as e:
        log.debug("MinIO bronze upload failed: %s", e)


def upload_silver(entity_id: str, source: str, sha: str, record: dict[str, Any]) -> None:
    minio = _get_minio()
    if minio is None:
        return
    try:
        minio.upload_silver(entity_id, source, sha, record)
    except Exception as e:
        log.debug("MinIO silver upload failed: %s", e)
