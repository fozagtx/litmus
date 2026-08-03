"""SQLite lookup index over the vault (data/litmus.db, WAL mode).

The index is a rebuildable cache — the vault is the source of truth.
``reindex_from_vault`` repopulates it entirely from sealed manifests and
anchors.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Iterator

from server import b2, config
from server.fingerprint import hamming, min_hamming
from server.schemas import SchemaValidationError, validate_locked
from server.signing import verify_obj

logger = logging.getLogger("litmus.index")

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False

_ASSET_COLUMNS = (
    "asset_id", "kind", "status", "sha256", "phash64", "phash_variants", "prompt", "provider",
    "model", "params_json", "created_utc", "run_id", "parent_asset",
    "manifest_key", "original_key", "thumb_key", "media_content_type",
    "retain_until", "anchor_batch",
)


def _connect() -> sqlite3.Connection:
    conn: sqlite3.Connection | None = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _local.conn = conn
    return conn


def init_db() -> None:
    global _initialized
    with _init_lock:
        conn = _connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                phash64 TEXT,
                phash_variants TEXT,
                prompt TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                params_json TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                run_id TEXT NOT NULL,
                parent_asset TEXT,
                manifest_key TEXT NOT NULL,
                original_key TEXT NOT NULL,
                thumb_key TEXT,
                media_content_type TEXT NOT NULL,
                retain_until TEXT NOT NULL,
                anchor_batch TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_assets_sha256 ON assets(sha256);
            CREATE INDEX IF NOT EXISTS idx_assets_parent ON assets(parent_asset);
            CREATE INDEX IF NOT EXISTS idx_assets_created ON assets(created_utc);
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                state_version INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        # Migration for databases created before pHash variants existed.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)")}
        if "phash_variants" not in cols:
            conn.execute("ALTER TABLE assets ADD COLUMN phash_variants TEXT")
        conn.commit()
        _initialized = True


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def upsert_asset(row: dict[str, Any]) -> None:
    values = {c: row.get(c) for c in _ASSET_COLUMNS}
    placeholders = ", ".join(f":{c}" for c in _ASSET_COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in _ASSET_COLUMNS if c != "asset_id")
    conn = _connect()
    conn.execute(
        f"INSERT INTO assets ({', '.join(_ASSET_COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(asset_id) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()


def get_asset(asset_id: str) -> dict[str, Any] | None:
    row = _connect().execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
    return _row_to_dict(row)


def get_by_sha256(sha256: str) -> dict[str, Any] | None:
    row = _connect().execute(
        "SELECT * FROM assets WHERE sha256 = ? ORDER BY (status = 'sealed') DESC, created_utc DESC LIMIT 1",
        (sha256,),
    ).fetchone()
    return _row_to_dict(row)


def phash_best_match(upload_hashes: list[str]) -> tuple[dict[str, Any], int] | None:
    """Linear scan over sealed image assets, min pairwise Hamming distance
    across pHash variants (full image + center crops on both sides).
    Best match <= threshold."""
    threshold = config.phash_max_distance()
    best: tuple[dict[str, Any], int] | None = None
    cur = _connect().execute(
        "SELECT * FROM assets WHERE kind = 'image' AND status = 'sealed' AND phash64 IS NOT NULL"
    )
    for row in cur:
        stored = [row["phash64"]]
        if row["phash_variants"]:
            try:
                stored = json.loads(row["phash_variants"]) or stored
            except ValueError:
                pass
        d = min_hamming(upload_hashes, stored)
        if d <= threshold and (best is None or d < best[1]):
            best = (dict(row), d)
            if d == 0:
                break
    return best


def list_assets(
    kind: str | None = None,
    include_discarded: bool = False,
    has_lineage: bool | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    args: list[Any] = []
    if not include_discarded:
        where.append("status = 'sealed'")
    if kind:
        where.append("kind = ?")
        args.append(kind)
    sql = "SELECT * FROM assets"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_utc DESC, asset_id DESC"
    rows = [dict(r) for r in _connect().execute(sql, args)]
    if has_lineage is not None:
        linked = _linked_asset_ids()
        rows = [
            r for r in rows
            if bool(r["asset_id"] in linked or r["parent_asset"]) == has_lineage
        ]
    return rows


def _linked_asset_ids() -> set[str]:
    cur = _connect().execute(
        "SELECT DISTINCT parent_asset FROM assets WHERE parent_asset IS NOT NULL"
    )
    return {r[0] for r in cur}


def children_of(asset_id: str, status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM assets WHERE parent_asset = ?"
    args: list[Any] = [asset_id]
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY created_utc ASC"
    return [dict(r) for r in _connect().execute(sql, args)]


def has_lineage(asset_id: str, parent_asset: str | None) -> bool:
    if parent_asset:
        return True
    row = _connect().execute(
        "SELECT 1 FROM assets WHERE parent_asset = ? LIMIT 1", (asset_id,)
    ).fetchone()
    return row is not None


def count_assets() -> int:
    return _connect().execute("SELECT COUNT(*) FROM assets").fetchone()[0]


def all_assets() -> list[dict[str, Any]]:
    return [dict(r) for r in _connect().execute("SELECT * FROM assets ORDER BY created_utc ASC")]


def unanchored_manifest_keys() -> list[tuple[str, str]]:
    """(manifest_key, asset_id) for sealed manifests not yet in any anchor."""
    cur = _connect().execute(
        "SELECT manifest_key, asset_id FROM assets WHERE anchor_batch IS NULL ORDER BY manifest_key"
    )
    return [(r[0], r[1]) for r in cur]


def set_anchor_batch(manifest_keys: list[str], batch: str) -> None:
    conn = _connect()
    conn.executemany(
        "UPDATE assets SET anchor_batch = ? WHERE manifest_key = ?",
        [(batch, k) for k in manifest_keys],
    )
    conn.commit()


def asset_by_manifest_key(manifest_key: str) -> dict[str, Any] | None:
    row = _connect().execute(
        "SELECT * FROM assets WHERE manifest_key = ?", (manifest_key,)
    ).fetchone()
    return _row_to_dict(row)


def anchor_batch_for(asset_id: str) -> str | None:
    row = _connect().execute(
        "SELECT anchor_batch FROM assets WHERE asset_id = ?", (asset_id,)
    ).fetchone()
    return row[0] if row else None


# --- runs -------------------------------------------------------------------

def upsert_run(run_id: str, status: str, created_utc: str, state_version: int) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO runs (run_id, status, created_utc, state_version) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, "
        "state_version=excluded.state_version",
        (run_id, status, created_utc, state_version),
    )
    conn.commit()


def list_run_ids() -> list[str]:
    return [r[0] for r in _connect().execute(
        "SELECT run_id FROM runs ORDER BY created_utc DESC"
    )]


# --- reindex ----------------------------------------------------------------

def _keys_for_kind(asset_id: str, kind: str) -> tuple[str, str | None]:
    if kind == "image":
        return f"assets/{asset_id}/original.png", f"assets/{asset_id}/thumb.webp"
    return f"assets/{asset_id}/narration.mp3", None


def reindex_from_vault() -> int:
    """Rebuild the assets table from lm-vault manifests + anchors.

    Returns the number of manifests indexed. Invalid or unverifiable
    manifests are skipped with a warning (they stay visible in the vault —
    the index only serves lookups).
    """
    init_db()
    count = 0
    for key in b2.list_keys("vault", "manifests/"):
        if not key.endswith(".json"):
            continue
        try:
            obj = b2.get_json("vault", key)
            validated = validate_locked(obj)
            if not verify_obj(validated):
                logger.warning("reindex: signature verification failed for %s; skipping", key)
                continue
        except (SchemaValidationError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("reindex: invalid manifest %s: %s; skipping", key, exc)
            continue
        original_key, thumb_key = _keys_for_kind(validated["asset_id"], validated["kind"])
        # Variants are derived from bytes, not stored in the manifest —
        # recompute from the original in lm-assets; fall back to the single hash.
        variants_json = None
        if validated["kind"] == "image":
            try:
                from server.fingerprint import phash_variants

                variants_json = json.dumps(
                    phash_variants(b2.get_bytes("assets", original_key))
                )
            except Exception as exc:  # noqa: BLE001 — index quality, not correctness
                logger.warning("reindex: could not derive variants for %s: %s", key, exc)
        upsert_asset(
            {
                "asset_id": validated["asset_id"],
                "kind": validated["kind"],
                "status": validated["status"],
                "sha256": validated["sha256"],
                "phash64": validated.get("phash64"),
                "phash_variants": variants_json,
                "prompt": validated["prompt"],
                "provider": validated["provider"],
                "model": validated["model"],
                "params_json": json.dumps(validated["params"], sort_keys=True),
                "created_utc": validated["created_utc"],
                "run_id": validated["run_id"],
                "parent_asset": validated.get("parent_asset"),
                "manifest_key": key,
                "original_key": original_key,
                "thumb_key": thumb_key,
                "media_content_type": validated["media_content_type"],
                "retain_until": validated["retain_until"],
                "anchor_batch": None,
            }
        )
        count += 1
    # Re-associate anchors.
    for key in b2.list_keys("vault", "anchors/"):
        if not key.endswith(".json"):
            continue
        try:
            anchor = validate_locked(b2.get_json("vault", key))
        except (SchemaValidationError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("reindex: invalid anchor %s: %s; skipping", key, exc)
            continue
        set_anchor_batch([leaf["key"] for leaf in anchor["leaves"]], anchor["batch"])
    logger.info("reindex complete: %d manifests indexed", count)
    return count
