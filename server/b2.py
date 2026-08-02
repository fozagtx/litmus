"""Backblaze B2 access — one lazy S3StorageBackend singleton per bucket role.

Roles:
    assets — lm-assets (no lock): media + thumbnails
    vault  — lm-vault  (Object Lock COMPLIANCE): manifests, receipts, anchors
    state  — lm-state  (no lock): resumable run state, export zips

``seal_json`` is the ONLY write path into the vault: it schema-validates
(R1), signs, canonicalizes, and puts with a per-object COMPLIANCE lock.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from genblaze import ObjectLockConfig

from server import config
from server.config import ConfigError
from server.schemas import validate_locked
from server.signing import canonical_bytes, sha256_hex, sign_obj

logger = logging.getLogger("litmus.b2")

_ROLE_TO_BUCKET_ENV = {
    "assets": "B2_ASSETS_BUCKET",
    "vault": "B2_VAULT_BUCKET",
    "state": "B2_STATE_BUCKET",
}

_backends: dict[str, Any] = {}
_lock = threading.Lock()


def _bucket_for(role: str) -> str:
    env_name = _ROLE_TO_BUCKET_ENV.get(role)
    if env_name is None:
        raise ValueError(f"Unknown bucket role {role!r}")
    config.require(f"b2_{role}")
    bucket = {
        "assets": config.assets_bucket,
        "vault": config.vault_bucket,
        "state": config.state_bucket,
    }[role]()
    assert bucket is not None  # require() guarantees it
    return bucket


def backend(role: str):
    """Lazy singleton S3StorageBackend for a bucket role.

    Raises ConfigError with a clear message when env vars are missing or the
    bucket is unreachable — never crashes at import time.
    """
    with _lock:
        cached = _backends.get(role)
        if cached is not None:
            return cached
        bucket = _bucket_for(role)
        try:
            from genblaze_s3 import S3StorageBackend

            be = S3StorageBackend.for_backblaze(
                bucket=bucket,
                region=config.b2_region(),
                key_id=config.b2_key_id(),
                app_key=config.b2_app_key(),
                preflight=True,
            )
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(
                f"Could not connect to B2 bucket {bucket!r} "
                f"(region {config.b2_region()!r}): {exc}"
            ) from exc
        _backends[role] = be
        return be


def reset_backends() -> None:
    """Drop cached backends (used by health checks after credential changes)."""
    with _lock:
        for be in _backends.values():
            try:
                be.close()
            except Exception:
                pass
        _backends.clear()


def vault_lock() -> ObjectLockConfig:
    """A fresh COMPLIANCE lock for now + VAULT_RETENTION_DAYS."""
    return ObjectLockConfig(
        retain_until=datetime.now(timezone.utc) + timedelta(days=config.vault_retention_days()),
        mode="COMPLIANCE",
    )


def seal_json(role: str, key: str, obj: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Schema-validate, sign, canonicalize and COMPLIANCE-lock a JSON object.

    Returns (signed_object, sha256_of_stored_bytes). Raises
    SchemaValidationError before any network I/O when the object is invalid
    (R1: never lock garbage), and StorageError/ConfigError on upload failure.
    """
    normalized = validate_locked(obj)
    signed = sign_obj(normalized)
    # Validate again WITH the signature so the exact stored shape is checked.
    signed = validate_locked(signed)
    data = canonical_bytes(signed)
    be = backend(role)
    be.put(key, data, content_type="application/json", object_lock=vault_lock())
    digest = sha256_hex(data)
    logger.info("sealed %s (%d bytes, sha256 %s…)", key, len(data), digest[:12])
    return signed, digest


def put_json(role: str, key: str, obj: dict[str, Any]) -> None:
    """Plain (unlocked) JSON write — lm-state only."""
    be = backend(role)
    be.put(key, canonical_bytes(obj), content_type="application/json")


def get_json(role: str, key: str) -> dict[str, Any]:
    be = backend(role)
    return json.loads(be.get(key).decode("utf-8"))


def get_bytes(role: str, key: str) -> bytes:
    return backend(role).get(key)


def exists(role: str, key: str) -> bool:
    return backend(role).exists(key)


def put_bytes(role: str, key: str, data: bytes, content_type: str) -> None:
    backend(role).put(key, data, content_type=content_type)


def list_keys(role: str, prefix: str) -> Iterator[str]:
    """Iterate every key under a prefix (handles pagination)."""
    be = backend(role)
    token: str | None = None
    while True:
        page = be.list(prefix, max_keys=1000, continuation_token=token)
        for entry in page.entries:
            yield entry.key
        token = page.next_token
        if token is None:
            return


def stream(role: str, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    yield from backend(role).stream(key, chunk_size=chunk_size)


def health_check(role: str) -> tuple[bool, str]:
    """Real connectivity check for /api/health: config + one LIST call."""
    missing = config.missing_for(f"b2_{role}")
    if missing:
        return False, f"missing env var{'s' if len(missing) > 1 else ''}: {', '.join(missing)}"
    try:
        be = backend(role)
        be.list("", max_keys=1)
        return True, f"bucket {_bucket_for(role)!r} reachable"
    except Exception as exc:
        return False, str(exc)
