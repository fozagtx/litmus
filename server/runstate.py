"""Run state · in-memory registry + lm-state persistence for resumability.

Every transition is persisted to ``runs/{run_id}/state.json`` in lm-state.
The persisted JSON is the public RunState shape plus a private ``_internal``
dict carrying resume bookkeeping (completed attempts, receipt chain cursor,
base seed). ``_internal`` never leaves the API.

The in-memory registry maps run_id -> RunEntry(state, internal, version,
condition) · the condition powers SSE: every mutation bumps the version and
notifies waiters.
"""

from __future__ import annotations

import logging
import secrets
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from server import b2, index
from server.schemas import RunState

logger = logging.getLogger("litmus.runstate")

TERMINAL_STATUSES = {"complete", "failed"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return "run_" + secrets.token_hex(5)


def new_asset_id() -> str:
    return "ast_" + secrets.token_hex(5)


class RunEntry:
    def __init__(self, state: RunState, internal: dict[str, Any], version: int = 0) -> None:
        self.state = state
        self.internal = internal
        self.version = version
        self.cond = threading.Condition()


_registry: dict[str, RunEntry] = {}
_registry_lock = threading.Lock()


def _state_key(run_id: str) -> str:
    return f"runs/{run_id}/state.json"


def _persist(entry: RunEntry) -> None:
    payload = entry.state.model_dump(mode="json")
    payload["_internal"] = entry.internal
    try:
        b2.put_json("state", _state_key(entry.state.run_id), payload)
    except Exception as exc:
        # The vault (sealed receipts) is the source of truth; state persistence
        # failing degrades resumability, not integrity. Log loudly, keep going.
        logger.error(
            "failed to persist run state %s to lm-state: %s", entry.state.run_id, exc
        )
    try:
        index.upsert_run(
            entry.state.run_id, entry.state.status, entry.state.created_utc, entry.version
        )
    except Exception as exc:
        logger.error("failed to upsert run row %s: %s", entry.state.run_id, exc)


def create_run(prompt: str, narration: bool, narration_text: str | None) -> RunState:
    run_id = new_run_id()
    ts = now_utc()
    state = RunState(
        run_id=run_id,
        status="queued",
        prompt=prompt,
        narration=narration,
        narration_text=narration_text,
        created_utc=ts,
        updated_utc=ts,
    )
    internal: dict[str, Any] = {
        "base_seed": secrets.randbelow(2**31),
        "seq": 0,
        "prev_receipt_sha256": None,
        "attempts": [],
        "narration_done": False,
        "narration_record": None,
        "final_sealed": False,
        "final_attempt_index": None,
    }
    entry = RunEntry(state, internal)
    with _registry_lock:
        _registry[run_id] = entry
    _persist(entry)
    return state


def get_entry(run_id: str) -> RunEntry | None:
    with _registry_lock:
        return _registry.get(run_id)


def get_state(run_id: str) -> RunState | None:
    entry = get_entry(run_id)
    return entry.state if entry else None


def list_states() -> list[RunState]:
    with _registry_lock:
        entries = list(_registry.values())
    states = [e.state for e in entries]
    states.sort(key=lambda s: (s.created_utc, s.run_id), reverse=True)
    return states


def mutate(run_id: str, fn: Callable[[RunState, dict[str, Any]], None]) -> RunState:
    """Apply ``fn(state, internal)`` under the run's lock, persist, notify SSE."""
    entry = get_entry(run_id)
    if entry is None:
        raise KeyError(f"Unknown run {run_id}")
    with entry.cond:
        fn(entry.state, entry.internal)
        entry.state.updated_utc = now_utc()
        entry.version += 1
        entry.cond.notify_all()
    _persist(entry)
    return entry.state


def wait_for_change(run_id: str, seen_version: int, timeout: float) -> int | None:
    """Block until the run's version exceeds ``seen_version`` (or timeout).

    Returns the new version, or None on timeout / unknown run.
    """
    entry = get_entry(run_id)
    if entry is None:
        return None
    with entry.cond:
        if entry.version > seen_version:
            return entry.version
        entry.cond.wait(timeout=timeout)
        return entry.version if entry.version > seen_version else None


def load_from_state_store(run_id: str) -> RunEntry | None:
    """Load a persisted run state from lm-state into the registry."""
    try:
        payload = b2.get_json("state", _state_key(run_id))
    except Exception:
        return None
    internal = payload.pop("_internal", {}) or {}
    try:
        state = RunState.model_validate(payload)
    except Exception as exc:
        logger.warning("invalid persisted state for %s: %s", run_id, exc)
        return None
    entry = RunEntry(state, internal)
    with _registry_lock:
        existing = _registry.get(run_id)
        if existing is not None:
            return existing
        _registry[run_id] = entry
    return entry


def load_all_from_state_store() -> list[RunEntry]:
    """Populate the registry from every ``runs/*/state.json`` in lm-state."""
    entries: list[RunEntry] = []
    seen: set[str] = set()
    for key in b2.list_keys("state", "runs/"):
        parts = key.split("/")
        if len(parts) == 3 and parts[2] == "state.json":
            run_id = parts[1]
            if run_id in seen:
                continue
            seen.add(run_id)
            entry = load_from_state_store(run_id)
            if entry is not None:
                entries.append(entry)
    return entries


def incomplete_run_ids() -> list[str]:
    with _registry_lock:
        return [
            rid for rid, e in _registry.items()
            if e.state.status not in TERMINAL_STATUSES
        ]
