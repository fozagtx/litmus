"""Pydantic schemas for every JSON object Litmus writes.

R1 mitigation: garbage locked in compliance storage is unfixable, so EVERY
object headed for the vault is validated against these models first
(see ``validate_locked`` / ``server.b2.seal_json``).

Wire shapes follow PRD §9.3. Two additive fields on the manifest beyond the
PRD's abbreviated sketch: ``status`` ("sealed" | "discarded") and
``media_content_type`` · both required for a lossless ``reindex_from_vault``
(the SQLite index is a cache; the vault must be self-describing).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PHASH_RE = re.compile(r"^[0-9a-f]{16}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _check_sha256(v: str) -> str:
    if not _SHA256_RE.match(v):
        raise ValueError(f"not a lowercase-hex sha256: {v!r}")
    return v


def _check_utc(v: str) -> str:
    if not _UTC_RE.match(v):
        raise ValueError(f"not a UTC ISO-8601 Z timestamp: {v!r}")
    return v


class ManifestV1(BaseModel):
    """litmus/manifest@1 · the asset birth certificate."""

    model_config = ConfigDict(extra="forbid")

    schema_: Literal["litmus/manifest@1"] = Field(alias="schema")
    asset_id: str = Field(min_length=4)
    created_utc: str
    creator_pubkey: str = Field(pattern=r"^ed25519:[A-Za-z0-9+/=]+$")
    kind: Literal["image", "audio"]
    status: Literal["sealed", "discarded"]
    prompt: str
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    params: dict[str, Any]
    sha256: str
    phash64: str | None = None
    media_content_type: str = Field(min_length=3)
    parent_asset: str | None = None
    run_id: str = Field(min_length=4)
    retain_until: str
    signature: str | None = None

    @field_validator("sha256")
    @classmethod
    def _v_sha(cls, v: str) -> str:
        return _check_sha256(v)

    @field_validator("phash64")
    @classmethod
    def _v_phash(cls, v: str | None) -> str | None:
        if v is not None and not _PHASH_RE.match(v):
            raise ValueError(f"not a 16-hex-char phash64: {v!r}")
        return v

    @field_validator("created_utc", "retain_until")
    @classmethod
    def _v_utc(cls, v: str) -> str:
        return _check_utc(v)


class ReceiptV1(BaseModel):
    """litmus/receipt@1 · one pipeline decision, hash-chained per run."""

    model_config = ConfigDict(extra="forbid")

    schema_: Literal["litmus/receipt@1"] = Field(alias="schema")
    run_id: str = Field(min_length=4)
    seq: int = Field(ge=0)
    step: Literal["generate", "judge", "narrate", "seal", "failure"]
    ts_utc: str
    provider: str = Field(min_length=1)
    model: str | None = None
    input_sha256: str
    output_sha256: str
    detail: dict[str, Any]
    prev_receipt_sha256: str | None = None
    signature: str | None = None

    @field_validator("input_sha256", "output_sha256")
    @classmethod
    def _v_sha(cls, v: str) -> str:
        return _check_sha256(v)

    @field_validator("prev_receipt_sha256")
    @classmethod
    def _v_prev(cls, v: str | None) -> str | None:
        if v is not None:
            return _check_sha256(v)
        return v

    @field_validator("ts_utc")
    @classmethod
    def _v_utc(cls, v: str) -> str:
        return _check_utc(v)


class AnchorLeaf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    sha256: str

    @field_validator("sha256")
    @classmethod
    def _v_sha(cls, v: str) -> str:
        return _check_sha256(v)


class AnchorV1(BaseModel):
    """litmus/anchor@1 · hourly Merkle root over newly sealed manifests."""

    model_config = ConfigDict(extra="forbid")

    schema_: Literal["litmus/anchor@1"] = Field(alias="schema")
    batch: str = Field(min_length=4)
    merkle_root: str
    leaf_count: int = Field(ge=1)
    leaves_prefix: Literal["manifests/"]
    leaves: list[AnchorLeaf] = Field(min_length=1)
    created_utc: str
    signature: str | None = None

    @field_validator("merkle_root")
    @classmethod
    def _v_root(cls, v: str) -> str:
        return _check_sha256(v)

    @field_validator("created_utc")
    @classmethod
    def _v_utc(cls, v: str) -> str:
        return _check_utc(v)


class ExportFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str
    size: int = Field(ge=0)

    @field_validator("sha256")
    @classmethod
    def _v_sha(cls, v: str) -> str:
        return _check_sha256(v)


class ExportV1(BaseModel):
    """litmus/export@1 · signed inventory of an exported archive."""

    model_config = ConfigDict(extra="forbid")

    schema_: Literal["litmus/export@1"] = Field(alias="schema")
    export_id: str = Field(min_length=4)
    created_utc: str
    creator_pubkey: str = Field(pattern=r"^ed25519:[A-Za-z0-9+/=]+$")
    files: list[ExportFile]
    signature: str | None = None

    @field_validator("created_utc")
    @classmethod
    def _v_utc(cls, v: str) -> str:
        return _check_utc(v)


# --- Run state (persisted to lm-state; NOT object-locked) -------------------

RunStatus = Literal["queued", "running", "complete", "failed"]
StepStatusStr = Literal["queued", "running", "passed", "retried", "failed", "discarded"]


class StepState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    name: str
    label: str
    provider: str | None = None
    model: str | None = None
    status: StepStatusStr
    started_utc: str | None = None
    ended_utc: str | None = None
    duration_ms: int | None = None
    receipt_key: str | None = None
    receipt_sha256: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    prompt: str
    narration: bool = False
    narration_text: str | None = None
    created_utc: str
    updated_utc: str
    steps: list[StepState] = Field(default_factory=list)
    asset_id: str | None = None
    audio_asset_id: str | None = None
    error: str | None = None


SCHEMAS: dict[str, type[BaseModel]] = {
    "litmus/manifest@1": ManifestV1,
    "litmus/receipt@1": ReceiptV1,
    "litmus/anchor@1": AnchorV1,
    "litmus/export@1": ExportV1,
}


class SchemaValidationError(ValueError):
    """Raised when an object destined for locked storage fails validation."""


def validate_locked(obj: dict[str, Any]) -> dict[str, Any]:
    """Validate an object against its declared litmus schema.

    Returns the round-tripped dict (by alias, exclude-none only for optional
    absent signature · the object is returned EXACTLY as it should be stored).
    Raises SchemaValidationError with detail on failure. This is the R1 gate:
    call it before every vault write.
    """
    tag = obj.get("schema")
    model = SCHEMAS.get(tag)  # type: ignore[arg-type]
    if model is None:
        raise SchemaValidationError(
            f"Object has unknown or missing schema tag {tag!r}; refusing to seal."
        )
    try:
        parsed = model.model_validate(obj)
    except Exception as exc:
        raise SchemaValidationError(f"{tag} validation failed: {exc}") from exc
    out = parsed.model_dump(by_alias=True)
    # ``schema_`` dumps as ``schema`` via alias; keep signature key even if None
    # out of the stored object only when actually present in the input.
    if obj.get("signature") is None and "signature" in out and out["signature"] is None:
        del out["signature"]
    return out
