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


# Center-crop fractions (per side) hashed alongside the full image. A crop of
# the upload lands near one of these zoom levels, so min-distance across
# variants recovers matches single-hash pHash misses (R2: measured a 24% total
# crop at distance 30 full-vs-full but 8 vs the 20% stored variant).
_VARIANT_FRACS = (0.05, 0.10, 0.15)


def phash_variants(data: bytes) -> list[str]:
    """pHashes of the full image plus center crops. First entry == phash64."""
    hashes = [phash64(data)]
    with Image.open(io.BytesIO(data)) as img:
        rgb = img.convert("RGB")
        w, h = rgb.size
        for frac in _VARIANT_FRACS:
            box = (int(w * frac), int(h * frac), int(w * (1 - frac)), int(h * (1 - frac)))
            crop = rgb.crop(box)
            hv = imagehash.phash(crop, hash_size=8)
            hashes.append(f"{int(str(hv), 16):016x}")
    return hashes


def min_hamming(a_hashes: list[str], b_hashes: list[str]) -> int:
    """Minimum pairwise Hamming distance across two variant sets."""
    return min(hamming(a, b) for a in a_hashes for b in b_hashes)
