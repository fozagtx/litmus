"""Merkle anchoring · hourly (and on-demand) roots over newly sealed manifests.

Leaves are the sha256 of each manifest object's bytes AS STORED in the vault,
sorted by key for determinism. Standard binary Merkle tree: node =
sha256(left_digest_bytes + right_digest_bytes); odd levels duplicate the last
node. Each anchor covers only the manifests sealed since the previous anchor
and embeds its leaves so inclusion proofs are computable from the anchor
object alone.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from server import b2, index
from server.fingerprint import sha256_hex

logger = logging.getLogger("litmus.merkle")

_anchor_lock = threading.Lock()
_anchor_cache: dict[str, dict[str, Any]] = {}  # batch -> anchor object


def _hash_pair(a_hex: str, b_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(a_hex) + bytes.fromhex(b_hex)).hexdigest()


def merkle_root(leaf_hashes: list[str]) -> str:
    """Root of a standard binary Merkle tree (duplicate last on odd)."""
    if not leaf_hashes:
        raise ValueError("merkle_root requires at least one leaf")
    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [_hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(leaf_hashes: list[str], leaf_index: int) -> list[dict[str, str]]:
    """Inclusion proof for ``leaf_hashes[leaf_index]``.

    Each entry: {"position": "left"|"right", "sha256": sibling_digest} · the
    sibling's position relative to the running hash.
    """
    if not (0 <= leaf_index < len(leaf_hashes)):
        raise ValueError(f"leaf_index {leaf_index} out of range")
    proof: list[dict[str, str]] = []
    level = list(leaf_hashes)
    idx = leaf_index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        sibling = idx + 1 if idx % 2 == 0 else idx - 1
        proof.append(
            {
                "position": "right" if idx % 2 == 0 else "left",
                "sha256": level[sibling],
            }
        )
        level = [_hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_proof(leaf_hash: str, proof: list[dict[str, str]], root: str) -> bool:
    acc = leaf_hash
    for step in proof:
        if step["position"] == "right":
            acc = _hash_pair(acc, step["sha256"])
        else:
            acc = _hash_pair(step["sha256"], acc)
    return acc == root


# --- anchoring --------------------------------------------------------------

def _batch_id(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H")


def anchor_new() -> dict[str, Any] | None:
    """Seal an anchor over manifests not yet covered by any anchor.

    Returns the signed anchor object, or None when there is nothing new.
    """
    with _anchor_lock:
        pending = index.unanchored_manifest_keys()
        if not pending:
            return None
        pending.sort(key=lambda pair: pair[0])  # sort by manifest key
        leaves: list[dict[str, str]] = []
        for manifest_key, _asset_id in pending:
            data = b2.get_bytes("vault", manifest_key)
            leaves.append({"key": manifest_key, "sha256": sha256_hex(data)})
        leaf_hashes = [leaf["sha256"] for leaf in leaves]
        root = merkle_root(leaf_hashes)
        now = datetime.now(timezone.utc)
        batch = _batch_id(now)
        anchor_key = f"anchors/{batch}.root.json"
        if b2.exists("vault", anchor_key):
            # A second anchor within the same hour (manual + hourly): keep the
            # hour-shaped id unique instead of stacking locked versions.
            batch = now.strftime("%Y-%m-%dT%H-%M%S")
            anchor_key = f"anchors/{batch}.root.json"
        anchor_obj = {
            "schema": "litmus/anchor@1",
            "batch": batch,
            "merkle_root": root,
            "leaf_count": len(leaves),
            "leaves_prefix": "manifests/",
            "leaves": leaves,
            "created_utc": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        signed, _digest = b2.seal_json("vault", anchor_key, anchor_obj)
        index.set_anchor_batch([leaf["key"] for leaf in leaves], batch)
        _anchor_cache[batch] = signed
        logger.info("anchored batch %s: %d leaves, root %s…", batch, len(leaves), root[:12])
        return signed


def load_anchor(batch: str) -> dict[str, Any] | None:
    cached = _anchor_cache.get(batch)
    if cached is not None:
        return cached
    key = f"anchors/{batch}.root.json"
    try:
        obj = b2.get_json("vault", key)
    except Exception:
        return None
    _anchor_cache[batch] = obj
    return obj


def list_anchors() -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for key in b2.list_keys("vault", "anchors/"):
        if not key.endswith(".root.json"):
            continue
        batch = key[len("anchors/"):-len(".root.json")]
        obj = load_anchor(batch)
        if obj is not None:
            anchors.append(obj)
    anchors.sort(key=lambda a: a.get("batch", ""), reverse=True)
    return anchors


def proof_for(manifest_key: str) -> dict[str, Any] | None:
    """Inclusion proof for a manifest, servable to the verify UI.

    Returns {"batch", "merkle_root", "anchor_key", "leaf": {...},
    "proof": [{position, sha256}, ...]} or None when not yet anchored.
    """
    asset = index.asset_by_manifest_key(manifest_key)
    if asset is None or not asset.get("anchor_batch"):
        return None
    batch = asset["anchor_batch"]
    anchor = load_anchor(batch)
    if anchor is None:
        return None
    leaves = anchor["leaves"]
    leaf_hashes = [leaf["sha256"] for leaf in leaves]
    leaf_index = next(
        (i for i, leaf in enumerate(leaves) if leaf["key"] == manifest_key), None
    )
    if leaf_index is None:
        return None
    return {
        "batch": batch,
        "merkle_root": anchor["merkle_root"],
        "anchor_key": f"anchors/{batch}.root.json",
        "leaf": leaves[leaf_index],
        "proof": merkle_proof(leaf_hashes, leaf_index),
    }
