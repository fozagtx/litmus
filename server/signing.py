"""Ed25519 signing for Litmus manifests, receipts, anchors and exports.

Canonical JSON is the byte-exact serialization signed and hashed everywhere:

    json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

Signatures are computed over the canonical JSON of the object WITHOUT its
``signature`` field, and stored base64 (standard alphabet) in ``signature``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

from server.config import ConfigError, signing_key_path

_lock = threading.Lock()
_private_key: Ed25519PrivateKey | None = None
_loaded_from: Path | None = None


def _normalize_numbers(obj: Any) -> Any:
    # Signed records are re-verified in the browser, where JSON.stringify
    # renders integral floats as integers (1.0 -> "1"). Coerce to match so
    # canonical bytes are identical across languages.
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, dict):
        return {k: _normalize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize_numbers(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    return json.dumps(
        _normalize_numbers(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def canonical_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_keypair(path: Path) -> Ed25519PrivateKey:
    """Generate a new Ed25519 keypair and write the private key PEM (0600)."""
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, pem)
    finally:
        os.close(fd)
    os.chmod(str(path), 0o600)
    return key


def _load_private_key() -> Ed25519PrivateKey:
    """Load (and cache) the Ed25519 private key.

    SIGNING_KEY_B64 (base64 of the PEM file) wins when set — this is how the
    key travels to PaaS deploys with ephemeral disks. Falls back to the file
    at SIGNING_KEY_PATH.
    """
    global _private_key, _loaded_from
    env_pem = os.environ.get("SIGNING_KEY_B64", "").strip()
    if env_pem:
        with _lock:
            if _private_key is not None and _loaded_from == Path("<env:SIGNING_KEY_B64>"):
                return _private_key
            try:
                key = serialization.load_pem_private_key(
                    base64.b64decode(env_pem), password=None
                )
            except Exception as exc:
                raise ConfigError(
                    f"SIGNING_KEY_B64 is set but not a base64-encoded Ed25519 PEM: {exc}"
                ) from exc
            if not isinstance(key, Ed25519PrivateKey):
                raise ConfigError("SIGNING_KEY_B64 is not an Ed25519 private key.")
            _private_key = key
            _loaded_from = Path("<env:SIGNING_KEY_B64>")
            return key
    path = signing_key_path()
    with _lock:
        if _private_key is not None and _loaded_from == path:
            return _private_key
        if not path.exists():
            raise ConfigError(
                f"Signing key not found at {path}. "
                "Generate one with: .venv/bin/python scripts/gen_keys.py"
            )
        try:
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        except Exception as exc:
            raise ConfigError(
                f"Could not load Ed25519 signing key from {path}: {exc}. "
                "Regenerate with: .venv/bin/python scripts/gen_keys.py --force"
            ) from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise ConfigError(
                f"Key at {path} is not an Ed25519 private key. "
                "Regenerate with: .venv/bin/python scripts/gen_keys.py --force"
            )
        _private_key = key
        _loaded_from = path
        return key


def signing_key_available() -> tuple[bool, str]:
    """Non-raising probe for /api/health. Returns (ok, detail)."""
    try:
        _load_private_key()
        return True, f"ed25519 key loaded ({fingerprint()})"
    except ConfigError as exc:
        return False, str(exc)


def sign_obj(obj: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``obj`` with a base64 Ed25519 ``signature`` field.

    The signature covers the canonical JSON of the object WITHOUT the
    ``signature`` field.
    """
    key = _load_private_key()
    unsigned = {k: v for k, v in obj.items() if k != "signature"}
    sig = key.sign(canonical_bytes(unsigned))
    signed = dict(unsigned)
    signed["signature"] = base64.b64encode(sig).decode("ascii")
    return signed


def verify_obj(obj: dict[str, Any], pubkey_b64: str | None = None) -> bool:
    """Verify the ``signature`` field of a signed object.

    Uses ``pubkey_b64`` (raw 32-byte base64) when given, otherwise the
    service's own public key.
    """
    sig_b64 = obj.get("signature")
    if not isinstance(sig_b64, str) or not sig_b64:
        return False
    try:
        sig = base64.b64decode(sig_b64, validate=True)
    except Exception:
        return False
    if pubkey_b64 is not None:
        try:
            pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pubkey_b64))
        except Exception:
            return False
    else:
        pub = _load_private_key().public_key()
    unsigned = {k: v for k, v in obj.items() if k != "signature"}
    try:
        pub.verify(sig, canonical_bytes(unsigned))
        return True
    except InvalidSignature:
        return False


def _raw_public_bytes() -> bytes:
    return _load_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def public_key_b64() -> str:
    """Base64 of the raw 32-byte Ed25519 public key."""
    return base64.b64encode(_raw_public_bytes()).decode("ascii")


def fingerprint() -> str:
    """First 16 hex chars of sha256 of the raw public key bytes."""
    return hashlib.sha256(_raw_public_bytes()).hexdigest()[:16]


def creator_pubkey_field() -> str:
    """Value stored in manifests' ``creator_pubkey``: ``ed25519:<base64>``."""
    return f"ed25519:{public_key_b64()}"
