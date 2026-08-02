"""Vault export — a signed, offline-verifiable archive of everything.

POST /api/export spawns a background thread that assembles the zip in a temp
dir, uploads it to lm-state ``exports/{export_id}.zip``, and records status
in an in-memory registry. The archive contains assets, manifests, receipts,
sdk-manifests, lineage.json, merkle proofs + anchors, an offline verify.py,
README.txt, and a signed litmus/export@1 inventory of every file.
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any

from server import b2, index, merkle
from server.fingerprint import sha256_hex
from server.runstate import now_utc
from server.schemas import validate_locked
from server.signing import canonical_bytes, creator_pubkey_field, sign_obj

logger = logging.getLogger("litmus.export")

TEMPLATE_VERIFY = Path(__file__).resolve().parent / "templates" / "verify.py"

_exports: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

README_TEXT = """Litmus vault export
===================

Your export contains every asset, manifest, receipt, and Merkle proof in
your vault, plus a small offline script that verifies all of it without us.
If Litmus disappeared tomorrow, this archive would still prove what you
made, and when.

Layout
------
assets/          Generated media (originals and narration audio), named by asset id.
manifests/       Signed litmus/manifest@1 birth certificates (canonical JSON, as sealed).
receipts/        Per-run signed receipt chains (litmus/receipt@1), hash-chained via
                 prev_receipt_sha256.
sdk-manifests/   Genblaze SDK manifests for the winning pipeline runs.
merkle-proofs/   Per-asset Merkle inclusion proofs and every sealed anchor object.
lineage.json     The asset lineage graph (parents, children, discarded candidates).
export-manifest.json
                 Signed litmus/export@1 inventory: SHA-256 of every file above.
verify.py        Offline verifier. Run: python3 verify.py
README.txt       This file.

Verification
------------
    python3 verify.py

Hashing and Merkle checks need only the Python standard library. Ed25519
signature checks additionally need the 'cryptography' package
(pip install cryptography).

Records in manifests/, receipts/, and merkle-proofs/anchors/ were written to
Backblaze B2 with Object Lock in COMPLIANCE mode: they could not be altered
or deleted at the source before their retention date, by anyone.
"""


def _ext_for(content_type: str, kind: str) -> str:
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "webp" in ct:
        return ".webp"
    if kind == "audio":
        return ".mp3"
    return ".bin"


def start_export() -> str:
    export_id = "exp_" + secrets.token_hex(5)
    with _lock:
        _exports[export_id] = {"status": "building", "error": None, "key": None}
    threading.Thread(
        target=_build, args=(export_id,), daemon=True, name=f"litmus-export-{export_id}"
    ).start()
    return export_id


def get_status(export_id: str) -> dict[str, Any] | None:
    with _lock:
        st = _exports.get(export_id)
        return dict(st) if st else None


def state_key(export_id: str) -> str:
    return f"exports/{export_id}.zip"


def _build(export_id: str) -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="litmus-export-"))
    try:
        root = tmpdir / "export"
        for sub in ("assets", "manifests", "receipts", "sdk-manifests", "merkle-proofs/anchors"):
            (root / sub).mkdir(parents=True, exist_ok=True)

        assets = index.all_assets()
        run_ids = sorted({a["run_id"] for a in assets})

        # assets/ — originals + narrations from lm-assets.
        for a in assets:
            ext = _ext_for(a["media_content_type"], a["kind"])
            data = b2.get_bytes("assets", a["original_key"])
            (root / "assets" / f"{a['asset_id']}{ext}").write_bytes(data)

        # manifests/ — exact sealed bytes from the vault.
        for a in assets:
            data = b2.get_bytes("vault", a["manifest_key"])
            (root / "manifests" / f"{a['asset_id']}.json").write_bytes(data)

        # receipts/ — per run, exact sealed bytes.
        for run_id in run_ids:
            run_dir = root / "receipts" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            for key in b2.list_keys("vault", f"receipts/{run_id}/"):
                if key.endswith(".json"):
                    (run_dir / key.rsplit("/", 1)[1]).write_bytes(b2.get_bytes("vault", key))

        # sdk-manifests/
        for key in b2.list_keys("vault", "sdk-manifests/"):
            if key.endswith(".json"):
                (root / "sdk-manifests" / key.rsplit("/", 1)[1]).write_bytes(
                    b2.get_bytes("vault", key)
                )

        # merkle-proofs/ — per-asset proof + all anchors.
        for key in b2.list_keys("vault", "anchors/"):
            if key.endswith(".json"):
                (root / "merkle-proofs" / "anchors" / key.rsplit("/", 1)[1]).write_bytes(
                    b2.get_bytes("vault", key)
                )
        for a in assets:
            proof = merkle.proof_for(a["manifest_key"])
            if proof is not None:
                (root / "merkle-proofs" / f"{a['asset_id']}.json").write_bytes(
                    canonical_bytes(proof)
                )

        # lineage.json
        lineage = {
            "generated_utc": now_utc(),
            "assets": [
                {
                    "asset_id": a["asset_id"],
                    "kind": a["kind"],
                    "status": a["status"],
                    "run_id": a["run_id"],
                    "parent_asset": a["parent_asset"],
                    "sha256": a["sha256"],
                    "phash64": a["phash64"],
                    "created_utc": a["created_utc"],
                }
                for a in assets
            ],
            "edges": [
                {"parent": a["parent_asset"], "child": a["asset_id"],
                 "relation": "discarded_candidate" if a["status"] == "discarded" else "derived"}
                for a in assets
                if a["parent_asset"]
            ],
        }
        (root / "lineage.json").write_bytes(canonical_bytes(lineage))

        # verify.py + README.txt
        shutil.copyfile(TEMPLATE_VERIFY, root / "verify.py")
        (root / "README.txt").write_text(README_TEXT, encoding="utf-8")

        # export-manifest.json — signed inventory of every file above.
        files = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                files.append(
                    {
                        "path": str(path.relative_to(root)),
                        "sha256": sha256_hex(data),
                        "size": len(data),
                    }
                )
        export_manifest = {
            "schema": "litmus/export@1",
            "export_id": export_id,
            "created_utc": now_utc(),
            "creator_pubkey": creator_pubkey_field(),
            "files": files,
        }
        normalized = validate_locked(export_manifest)
        signed = sign_obj(normalized)
        (root / "export-manifest.json").write_bytes(canonical_bytes(signed))

        # zip + upload to lm-state.
        zip_path = tmpdir / f"{export_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(root)))
        with open(zip_path, "rb") as fh:
            b2.backend("state").put(state_key(export_id), fh, content_type="application/zip")

        with _lock:
            _exports[export_id] = {
                "status": "ready",
                "error": None,
                "key": state_key(export_id),
            }
        logger.info("export %s ready (%d files)", export_id, len(files))
    except Exception as exc:  # noqa: BLE001 — recorded honestly in status
        logger.exception("export %s failed", export_id)
        with _lock:
            _exports[export_id] = {"status": "failed", "error": str(exc), "key": None}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
