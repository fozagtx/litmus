#!/usr/bin/env python3
"""Offline verifier for a Litmus vault export.

Run from the root of the extracted export:

    python3 verify.py [--require-signatures]

Checks, in order:
  1. Every file listed in export-manifest.json exists and matches its SHA-256.
  2. Every manifest's Ed25519 signature (needs the `cryptography` package;
     without it, signature checks are skipped unless --require-signatures).
  3. Every run's receipt chain: per-run seq ordering and
     prev_receipt_sha256 == sha256 of the previous receipt's canonical JSON.
  4. Every Merkle anchor: root recomputed from its embedded leaves, and each
     leaf's sha256 matches the exported manifest file bytes.

Only the Python standard library is required for hashing and Merkle checks.
Exits 0 when everything verifies; 1 otherwise.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PASS = "ok"
FAIL = "FAIL"

failures: list[str] = []
checked_records = 0


def _normalize_numbers(obj):
    # Match the sealing service and the in-browser verifier: integral floats
    # canonicalize as integers (1.0 -> "1") so bytes agree across languages.
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    if isinstance(obj, dict):
        return {k: _normalize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_numbers(v) for v in obj]
    return obj


def canonical_bytes(obj) -> bytes:
    return json.dumps(
        _normalize_numbers(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"  {FAIL}: {msg}")


def load_json(path: Path):
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def try_import_ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        return Ed25519PublicKey
    except ImportError:
        return None


def verify_signature(obj, pubkey_raw: bytes, Ed25519PublicKey) -> bool:
    sig_b64 = obj.get("signature")
    if not sig_b64:
        return False
    unsigned = {k: v for k, v in obj.items() if k != "signature"}
    try:
        pub = Ed25519PublicKey.from_public_bytes(pubkey_raw)
        pub.verify(base64.b64decode(sig_b64), canonical_bytes(unsigned))
        return True
    except Exception:
        return False


def merkle_root(leaf_hashes):
    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            hashlib.sha256(bytes.fromhex(level[i]) + bytes.fromhex(level[i + 1])).hexdigest()
            for i in range(0, len(level), 2)
        ]
    return level[0]


def main() -> int:
    global checked_records
    parser = argparse.ArgumentParser(description="Verify a Litmus vault export offline.")
    parser.add_argument(
        "--require-signatures",
        action="store_true",
        help="Fail (instead of skipping) when the cryptography package is unavailable.",
    )
    args = parser.parse_args()

    manifest_path = ROOT / "export-manifest.json"
    if not manifest_path.exists():
        print(f"{FAIL}: export-manifest.json not found next to verify.py")
        return 1
    export_manifest = load_json(manifest_path)

    pubkey_field = export_manifest.get("creator_pubkey", "")
    if not pubkey_field.startswith("ed25519:"):
        print(f"{FAIL}: export-manifest.json has no ed25519 creator_pubkey")
        return 1
    pubkey_raw = base64.b64decode(pubkey_field[len("ed25519:"):])
    print(
        "Creator public key fingerprint:",
        hashlib.sha256(pubkey_raw).hexdigest()[:16],
    )
    print(
        "Note: the public key is read from this archive. To bind it to the "
        "service, compare the fingerprint above with the one published at "
        "/api/pubkey."
    )

    Ed25519PublicKey = try_import_ed25519()
    if Ed25519PublicKey is None:
        if args.require_signatures:
            print(
                f"{FAIL}: the 'cryptography' package is required for signature "
                "verification. Install it with:\n    pip install cryptography"
            )
            return 1
        print(
            "WARNING: 'cryptography' not installed — signature checks skipped. "
            "Install with: pip install cryptography"
        )

    # 1. File inventory ------------------------------------------------------
    print("\n[1/4] File inventory vs export-manifest.json")
    for entry in export_manifest.get("files", []):
        path = ROOT / entry["path"]
        if not path.exists():
            fail(f"missing file: {entry['path']}")
            continue
        data = path.read_bytes()
        if sha256_hex(data) != entry["sha256"]:
            fail(f"sha256 mismatch: {entry['path']}")
            continue
        if entry.get("size") is not None and len(data) != entry["size"]:
            fail(f"size mismatch: {entry['path']}")
            continue
        checked_records += 1
    print(f"  {len(export_manifest.get('files', []))} files listed")

    # Export manifest's own signature.
    if Ed25519PublicKey is not None:
        if verify_signature(export_manifest, pubkey_raw, Ed25519PublicKey):
            checked_records += 1
        else:
            fail("export-manifest.json signature invalid")

    # 2. Manifest signatures -------------------------------------------------
    print("\n[2/4] Manifest signatures")
    manifest_dir = ROOT / "manifests"
    manifest_bytes: dict[str, bytes] = {}
    for path in sorted(manifest_dir.glob("*.json")) if manifest_dir.exists() else []:
        data = path.read_bytes()
        manifest_bytes[f"manifests/{path.name}"] = data
        obj = json.loads(data.decode("utf-8"))
        if obj.get("schema") != "litmus/manifest@1":
            fail(f"{path.name}: unexpected schema {obj.get('schema')!r}")
            continue
        if Ed25519PublicKey is not None:
            if not verify_signature(obj, pubkey_raw, Ed25519PublicKey):
                fail(f"{path.name}: signature invalid")
                continue
        checked_records += 1
    print(f"  {len(manifest_bytes)} manifests checked")

    # 3. Receipt chains ------------------------------------------------------
    print("\n[3/4] Receipt chains")
    receipts_dir = ROOT / "receipts"
    run_count = 0
    if receipts_dir.exists():
        for run_dir in sorted(p for p in receipts_dir.iterdir() if p.is_dir()):
            run_count += 1
            prev_hash = None
            prev_seq = -1
            for path in sorted(run_dir.glob("*.json")):
                data = path.read_bytes()
                obj = json.loads(data.decode("utf-8"))
                rel = f"receipts/{run_dir.name}/{path.name}"
                if obj.get("schema") != "litmus/receipt@1":
                    fail(f"{rel}: unexpected schema")
                    continue
                if obj.get("seq") <= prev_seq:
                    fail(f"{rel}: seq {obj.get('seq')} not increasing")
                if obj.get("prev_receipt_sha256") != prev_hash:
                    fail(f"{rel}: prev_receipt_sha256 does not match prior receipt")
                if Ed25519PublicKey is not None and not verify_signature(
                    obj, pubkey_raw, Ed25519PublicKey
                ):
                    fail(f"{rel}: signature invalid")
                prev_hash = sha256_hex(canonical_bytes(obj))
                prev_seq = obj.get("seq", prev_seq)
                checked_records += 1
    print(f"  {run_count} runs checked")

    # 4. Merkle anchors ------------------------------------------------------
    print("\n[4/4] Merkle anchors")
    anchors_dir = ROOT / "merkle-proofs" / "anchors"
    anchor_count = 0
    if anchors_dir.exists():
        for path in sorted(anchors_dir.glob("*.json")):
            anchor = load_json(path)
            if anchor.get("schema") != "litmus/anchor@1":
                fail(f"{path.name}: unexpected schema")
                continue
            leaves = anchor.get("leaves", [])
            if not leaves:
                fail(f"{path.name}: no leaves")
                continue
            root = merkle_root([leaf["sha256"] for leaf in leaves])
            if root != anchor.get("merkle_root"):
                fail(f"{path.name}: recomputed root does not match merkle_root")
                continue
            for leaf in leaves:
                data = manifest_bytes.get(leaf["key"])
                if data is None:
                    # Anchors may cover manifests outside this export slice.
                    continue
                if sha256_hex(data) != leaf["sha256"]:
                    fail(f"{path.name}: leaf {leaf['key']} does not match exported bytes")
            if Ed25519PublicKey is not None and not verify_signature(
                anchor, pubkey_raw, Ed25519PublicKey
            ):
                fail(f"{path.name}: signature invalid")
                continue
            anchor_count += 1
            checked_records += 1
    print(f"  {anchor_count} anchors checked")

    total = checked_records + len(failures)
    print()
    if failures:
        print(f"{checked_records}/{total} records verified — {len(failures)} FAILURE(S)")
        return 1
    print(f"{checked_records}/{checked_records} records verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
