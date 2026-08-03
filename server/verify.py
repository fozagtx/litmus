"""Public verification — PRD §6.6 / §9.6.

Lookup order: exact SHA-256 → perceptual (pHash Hamming ≤ threshold, images
only) → none. The uploaded file is NEVER stored (R6). 25 MB cap, in-memory
per-IP rate limit (30 verifies/min → 429).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from server import b2, config, index, merkle
from server.fingerprint import phash64, phash_variants, sha256_hex

logger = logging.getLogger("litmus.verify")

MAX_VERIFY_BYTES = 25 * 1024 * 1024  # PRD §8.6 / R6
RATE_LIMIT_PER_MIN = 30

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

_rate_lock = threading.Lock()
_rate: dict[str, deque[float]] = {}


class VerifyRejected(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        q = _rate.setdefault(ip, deque())
        while q and now - q[0] > 60.0:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MIN:
            raise VerifyRejected(429, "Rate limit exceeded: 30 verifications per minute per IP.")
        q.append(now)
        # Opportunistic cleanup so the map cannot grow unbounded.
        if len(_rate) > 10_000:
            stale = [k for k, v in _rate.items() if not v or now - v[-1] > 120]
            for k in stale:
                del _rate[k]


def classify_content_type(content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in ALLOWED_IMAGE_TYPES:
        return "image"
    if ct.startswith("audio/"):
        return "audio"
    raise VerifyRejected(
        415,
        f"Unsupported content type {ct or '(none)'!r}. "
        "Accepted: image/png, image/jpeg, image/webp, or audio/*.",
    )


def asset_summary(row: dict[str, Any]) -> dict[str, Any]:
    thumb = f"/api/media/{row['asset_id']}/thumb.webp" if row.get("thumb_key") else None
    media_name = "original.png" if row["kind"] == "image" else "narration.mp3"
    return {
        "asset_id": row["asset_id"],
        "kind": row["kind"],
        "status": row["status"],
        "prompt": row["prompt"],
        "created_utc": row["created_utc"],
        "thumb_url": thumb,
        "media_url": f"/api/media/{row['asset_id']}/{media_name}",
        "sha256": row["sha256"],
        "phash64": row.get("phash64"),
        "retain_until": row["retain_until"],
        "has_lineage": index.has_lineage(row["asset_id"], row.get("parent_asset")),
        "parent_asset": row.get("parent_asset"),
        "run_id": row["run_id"],
    }


def _load_manifest(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return b2.get_json("vault", row["manifest_key"])
    except Exception as exc:
        logger.error("could not load manifest %s: %s", row["manifest_key"], exc)
        return None


def load_receipts(run_id: str) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    try:
        for key in b2.list_keys("vault", f"receipts/{run_id}/"):
            if not key.endswith(".json"):
                continue
            try:
                receipts.append(b2.get_json("vault", key))
            except Exception as exc:
                logger.error("could not load receipt %s: %s", key, exc)
    except Exception as exc:
        logger.error("could not list receipts for %s: %s", run_id, exc)
    receipts.sort(key=lambda r: r.get("seq", 0))
    return receipts


def _match_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset": asset_summary(row),
        "manifest": _load_manifest(row),
        "receipts": load_receipts(row["run_id"]),
        "anchor": merkle.proof_for(row["manifest_key"]),
    }


def verify_bytes(data: bytes, content_type: str | None) -> dict[str, Any]:
    """Compute the verdict payload for an uploaded file. Never stores it."""
    if len(data) > MAX_VERIFY_BYTES:
        raise VerifyRejected(
            413, "Files up to 25 MB for now. For anything larger, verification by hash is in the docs.",
        )
    if not data:
        raise VerifyRejected(400, "Empty upload.")
    kind = classify_content_type(content_type)

    sha = sha256_hex(data)
    uploaded: dict[str, Any] = {"sha256": sha}

    exact = index.get_by_sha256(sha)
    if exact is not None:
        if kind == "image":
            try:
                uploaded["phash64"] = phash64(data)
            except Exception:
                pass
        return {"verdict": "exact", "uploaded": uploaded, **_match_payload(exact)}

    if kind == "image":
        try:
            upload_hashes = phash_variants(data)
        except Exception as exc:
            raise VerifyRejected(400, f"Could not decode the image: {exc}") from exc
        uploaded["phash64"] = upload_hashes[0]
        best = index.phash_best_match(upload_hashes)
        if best is not None:
            row, distance = best
            return {
                "verdict": "perceptual",
                "similarity": round(1 - distance / 64, 4),
                "distance": distance,
                "uploaded": uploaded,
                **_match_payload(row),
            }

    return {"verdict": "none", "uploaded": uploaded}
