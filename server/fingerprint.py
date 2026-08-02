"""Content fingerprinting: SHA-256 and 64-bit perceptual hash (pHash)."""

from __future__ import annotations

import hashlib
import io

import imagehash
from PIL import Image


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def phash64(data: bytes) -> str:
    """64-bit perceptual hash of image bytes as 16 lowercase hex chars.

    Raises ``PIL.UnidentifiedImageError`` (or OSError) when the bytes are not
    a decodable image — callers decide how to surface that.
    """
    with Image.open(io.BytesIO(data)) as img:
        h = imagehash.phash(img.convert("RGB"), hash_size=8)
    return f"{int(str(h), 16):016x}"


def hamming(a_hex: str, b_hex: str) -> int:
    """Hamming distance between two 64-bit hex-encoded hashes."""
    return bin(int(a_hex, 16) ^ int(b_hex, 16)).count("1")
