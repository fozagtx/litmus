#!/usr/bin/env python3
"""Local smoke test, NO network. Exercises signing, canonical JSON,
fingerprinting, Merkle, SQLite index, receipt chaining, and schema
validation. Exits nonzero on any failure."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Isolate from any real deployment BEFORE importing server modules.
_TMP = tempfile.mkdtemp(prefix="litmus-smoke-")
os.environ["SIGNING_KEY_PATH"] = os.path.join(_TMP, "signing_key.pem")
os.environ["LITMUS_DB_PATH"] = os.path.join(_TMP, "litmus.db")

FAILURES: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  ok: {name}")
    except AssertionError as exc:
        FAILURES.append(f"{name}: {exc}")
        print(f"  FAIL: {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{name}: unexpected {type(exc).__name__}: {exc}")
        print(f"  FAIL: {name}: unexpected {type(exc).__name__}: {exc}")


# --- signing ---------------------------------------------------------------

def test_signing_roundtrip() -> None:
    from server.signing import generate_keypair, public_key_b64, sign_obj, verify_obj

    generate_keypair(Path(os.environ["SIGNING_KEY_PATH"]))
    obj = {"schema": "litmus/receipt@1", "b": 2, "a": [1, "χ"], "nested": {"y": None}}
    signed = sign_obj(obj)
    assert "signature" in signed and signed["signature"], "no signature produced"
    assert verify_obj(signed), "valid signature failed verification"
    assert verify_obj(signed, pubkey_b64=public_key_b64()), "explicit-pubkey verify failed"


def test_tamper_detection() -> None:
    from server.signing import sign_obj, verify_obj

    signed = sign_obj({"value": 41, "who": "litmus"})
    tampered = dict(signed)
    tampered["value"] = 42
    assert not verify_obj(tampered), "tampered object passed verification"
    bad_sig = dict(signed)
    bad_sig["signature"] = "A" * 86 + "=="
    assert not verify_obj(bad_sig), "garbage signature passed verification"


def test_canonical_stability() -> None:
    from server.signing import canonical_bytes

    a = {"z": 1, "a": {"c": [1, 2, 3], "b": "é"}, "m": None}
    b = {"a": {"b": "é", "c": [1, 2, 3]}, "m": None, "z": 1}
    assert canonical_bytes(a) == canonical_bytes(b), "key order changed canonical bytes"
    assert canonical_bytes(a) == canonical_bytes(a), "canonicalization not deterministic"
    assert b'"\xc3\xa9"' in canonical_bytes(a), "ensure_ascii leaked into canonical form"


def test_key_fingerprint() -> None:
    import base64

    from server.signing import fingerprint, public_key_b64

    raw = base64.b64decode(public_key_b64())
    assert len(raw) == 32, f"raw pubkey is {len(raw)} bytes, want 32"
    fp = fingerprint()
    assert len(fp) == 16 and all(c in "0123456789abcdef" for c in fp), f"bad fingerprint {fp!r}"


# --- fingerprinting --------------------------------------------------------

def _gradient_image(size: int = 512) -> bytes:
    """A structured, photo-like test pattern (pure gradients are pathological
    for DCT-based pHash, real photos tolerate crops far better)."""
    import io
    import math

    from PIL import Image

    img = Image.new("RGB", (size, size))
    px = img.load()
    for x in range(size):
        for y in range(size):
            v = (
                math.sin(x / 37) + math.cos(y / 29)
                + math.sin((x + y) / 53) + math.cos((x - y) / 41)
            )
            c = int((v + 4) / 8 * 255)
            px[x, y] = (c, 255 - c, (c * 3) % 255)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _checkerboard_image(size: int = 512, cell: int = 32) -> bytes:
    import io

    from PIL import Image

    img = Image.new("RGB", (size, size))
    px = img.load()
    for x in range(size):
        for y in range(size):
            on = ((x // cell) + (y // cell)) % 2 == 0
            px[x, y] = (255, 255, 255) if on else (0, 0, 0)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_phash() -> None:
    import io

    from PIL import Image

    from server import config
    from server.fingerprint import hamming, phash64, sha256_hex

    grad = _gradient_image()
    assert len(sha256_hex(grad)) == 64
    h1 = phash64(grad)
    h2 = phash64(grad)
    assert len(h1) == 16, f"phash64 length {len(h1)}, want 16 hex chars"
    assert h1 == h2 and hamming(h1, h2) == 0, "identical images must have distance 0"

    with Image.open(io.BytesIO(grad)) as img:
        cropped = img.crop((0, 0, 502, 502))  # cropped copy
        out = io.BytesIO()
        cropped.save(out, format="JPEG", quality=70)  # re-compressed too
        resized = io.BytesIO()
        img.resize((300, 300)).save(resized, format="JPEG", quality=60)
    h_crop = phash64(out.getvalue())
    d = hamming(h1, h_crop)
    assert d <= config.phash_max_distance(), (
        f"cropped copy distance {d} > threshold {config.phash_max_distance()}"
    )
    d_resize = hamming(h1, phash64(resized.getvalue()))
    assert d_resize <= config.phash_max_distance(), (
        f"resized+recompressed distance {d_resize} > threshold"
    )

    h_other = phash64(_checkerboard_image())
    assert hamming(h1, h_other) > config.phash_max_distance(), (
        "distinct images collided within threshold"
    )


# --- Merkle ----------------------------------------------------------------

def test_merkle() -> None:
    from server.fingerprint import sha256_hex
    from server.merkle import merkle_proof, merkle_root, verify_proof

    for n in (1, 2, 3, 5, 8):
        leaves = [sha256_hex(f"leaf-{i}".encode()) for i in range(n)]
        root = merkle_root(leaves)
        assert len(root) == 64
        for i in range(n):
            proof = merkle_proof(leaves, i)
            assert verify_proof(leaves[i], proof, root), f"proof failed n={n} i={i}"
            if n > 1:
                wrong = sha256_hex(b"not-a-leaf")
                assert not verify_proof(wrong, proof, root), "wrong leaf verified"
    # Determinism: same leaves, same root.
    leaves = [sha256_hex(f"leaf-{i}".encode()) for i in range(4)]
    assert merkle_root(leaves) == merkle_root(list(leaves)), "root not deterministic"


# --- SQLite index ----------------------------------------------------------

def _asset_row(asset_id: str, sha: str, ph: str | None, status: str = "sealed",
               kind: str = "image", parent: str | None = None) -> dict:
    return {
        "asset_id": asset_id, "kind": kind, "status": status, "sha256": sha,
        "phash64": ph, "prompt": "a lighthouse at dawn", "provider": "pollinations",
        "model": "seedream-4-0", "params_json": "{}",
        "created_utc": "2026-08-02T12:00:00Z", "run_id": "run_smoke01",
        "parent_asset": parent, "manifest_key": f"manifests/{asset_id}.json",
        "original_key": f"assets/{asset_id}/original.png",
        "thumb_key": f"assets/{asset_id}/thumb.webp",
        "media_content_type": "image/png", "retain_until": "2026-08-09T12:00:00Z",
        "anchor_batch": None,
    }


def test_index() -> None:
    from server import index
    from server.fingerprint import hamming, phash64, sha256_hex

    index.init_db()
    grad = _gradient_image()
    sha = sha256_hex(grad)
    ph = phash64(grad)
    index.upsert_asset(_asset_row("ast_smoke0001", sha, ph))
    index.upsert_asset(_asset_row("ast_smoke0002", sha256_hex(b"other"),
                                  phash64(_checkerboard_image())))
    index.upsert_asset(_asset_row("ast_smoke0003", sha256_hex(b"discarded"), ph,
                                  status="discarded", parent="ast_smoke0001"))

    got = index.get_by_sha256(sha)
    assert got and got["asset_id"] == "ast_smoke0001", "exact sha256 lookup failed"

    near = ph[:-1] + ("0" if ph[-1] != "0" else "1")  # flip low bits
    best = index.phash_best_match([near])
    assert best is not None, "near phash found no match"
    row, dist = best
    assert row["asset_id"] == "ast_smoke0001", f"wrong best match {row['asset_id']}"
    assert dist == hamming(ph, near), "distance mismatch"

    # Variant matching: a heavy center crop must match through the stored
    # pHash variants even when the full-frame distance exceeds the threshold.
    import io
    import json as _json

    from PIL import Image

    from server import config
    from server.fingerprint import phash_variants

    with Image.open(io.BytesIO(grad)) as img:
        w, h = img.size
        heavy = img.crop((int(w * 0.12), int(h * 0.12), int(w * 0.88), int(h * 0.88)))
        buf = io.BytesIO()
        heavy.convert("RGB").resize((400, 400)).save(buf, format="JPEG", quality=62)
    upload_hashes = phash_variants(buf.getvalue())
    row_v = _asset_row("ast_smoke0004", sha256_hex(b"variant-src"), ph)
    row_v["phash_variants"] = _json.dumps(phash_variants(grad))
    index.upsert_asset(row_v)
    best_v = index.phash_best_match(upload_hashes)
    assert best_v is not None, "variant matching found nothing for a heavy crop"
    assert best_v[1] <= config.phash_max_distance(), f"variant distance {best_v[1]} over threshold"

    # Discarded assets must not appear in perceptual matches or default lists.
    listed = index.list_assets()
    assert all(r["status"] == "sealed" for r in listed), "discarded leaked into list"
    assert index.has_lineage("ast_smoke0001", None), "parent lineage not detected"
    assert len(index.children_of("ast_smoke0001", status="discarded")) == 1


# --- receipt chain ---------------------------------------------------------

def test_receipt_chain() -> None:
    from server.fingerprint import sha256_hex
    from server.schemas import validate_locked
    from server.signing import canonical_bytes, sign_obj, verify_obj

    prev = None
    stored: list[dict] = []
    for seq, step in enumerate(["generate", "judge", "seal"]):
        obj = {
            "schema": "litmus/receipt@1",
            "run_id": "run_smoke01",
            "seq": seq,
            "step": step,
            "ts_utc": "2026-08-02T12:00:00Z",
            "provider": "pollinations",
            "model": "seedream-4-0",
            "input_sha256": sha256_hex(f"in{seq}".encode()),
            "output_sha256": sha256_hex(f"out{seq}".encode()),
            "detail": {"attempt": 0},
            "prev_receipt_sha256": prev,
        }
        signed = sign_obj(validate_locked(obj))
        signed = validate_locked(signed)
        stored.append(signed)
        prev = sha256_hex(canonical_bytes(signed))

    # Verify the chain the way the offline verifier does.
    prev = None
    for signed in stored:
        assert signed["prev_receipt_sha256"] == prev, "chain link mismatch"
        assert verify_obj(signed), "receipt signature invalid"
        prev = sha256_hex(canonical_bytes(signed))

    # A tampered middle receipt must break the next link.
    tampered = dict(stored[1])
    tampered["detail"] = {"attempt": 99}
    assert sha256_hex(canonical_bytes(tampered)) != stored[2]["prev_receipt_sha256"], (
        "tampering did not break the chain"
    )


# --- schemas ---------------------------------------------------------------

def test_schemas() -> None:
    from server.fingerprint import sha256_hex
    from server.schemas import SchemaValidationError, validate_locked
    from server.signing import creator_pubkey_field

    manifest = {
        "schema": "litmus/manifest@1",
        "asset_id": "ast_smoke0001",
        "created_utc": "2026-08-02T12:00:00Z",
        "creator_pubkey": creator_pubkey_field(),
        "kind": "image",
        "status": "sealed",
        "prompt": "a lighthouse at dawn",
        "provider": "pollinations",
        "model": "seedream-4-0",
        "params": {"seed": 8812, "size": "1024x1024"},
        "sha256": sha256_hex(b"img"),
        "phash64": "d1b2c3a4e5f60718",
        "media_content_type": "image/png",
        "parent_asset": None,
        "run_id": "run_smoke01",
        "retain_until": "2026-08-09T12:00:00Z",
    }
    out = validate_locked(manifest)
    assert out["schema"] == "litmus/manifest@1"

    for bad_mutation, desc in [
        ({"sha256": "NOT-HEX"}, "bad sha256"),
        ({"created_utc": "yesterday"}, "bad timestamp"),
        ({"kind": "video"}, "unknown kind"),
        ({"schema": "litmus/manifest@2"}, "unknown schema tag"),
    ]:
        candidate = {**manifest, **bad_mutation}
        try:
            validate_locked(candidate)
            raise AssertionError(f"{desc} was accepted")
        except SchemaValidationError:
            pass

    missing = dict(manifest)
    del missing["prompt"]
    try:
        validate_locked(missing)
        raise AssertionError("missing prompt was accepted")
    except SchemaValidationError:
        pass

    anchor = {
        "schema": "litmus/anchor@1",
        "batch": "2026-08-02T14",
        "merkle_root": sha256_hex(b"root"),
        "leaf_count": 1,
        "leaves_prefix": "manifests/",
        "leaves": [{"key": "manifests/ast_smoke0001.json", "sha256": sha256_hex(b"m")}],
        "created_utc": "2026-08-02T14:00:00Z",
    }
    validate_locked(anchor)

    export = {
        "schema": "litmus/export@1",
        "export_id": "exp_smoke0001",
        "created_utc": "2026-08-02T15:00:00Z",
        "creator_pubkey": creator_pubkey_field(),
        "files": [{"path": "README.txt", "sha256": sha256_hex(b"r"), "size": 1}],
    }
    validate_locked(export)


def main() -> int:
    print("Litmus local smoke test (no network)\n")
    check("signing round trip", test_signing_roundtrip)
    check("tamper detection", test_tamper_detection)
    check("canonical JSON stability", test_canonical_stability)
    check("key fingerprint format", test_key_fingerprint)
    check("phash identity / crop / distinctness", test_phash)
    check("merkle build + proof verify", test_merkle)
    check("sqlite index insert + lookup", test_index)
    check("receipt chain build + verify", test_receipt_chain)
    check("schema validation gates", test_schemas)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
