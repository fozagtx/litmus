"""Configuration for the Litmus backend.

All values are read from environment variables (loaded from the project-root
.env via python-dotenv). Importing this module NEVER raises on missing
credentials · validation is lazy, per subsystem, via :func:`require` so that
/api/health can report exactly what is missing and endpoints can 503 with a
clear message naming the env var.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load .env from the project root. override=False: real environment wins.
load_dotenv(PROJECT_ROOT / ".env", override=False)


class ConfigError(RuntimeError):
    """Raised when a required environment variable is missing or invalid."""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None and value.strip() == "":
        value = None
    return value if value is not None else default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


# --- Backblaze B2 -----------------------------------------------------------

def b2_region() -> str | None:
    return _env("B2_REGION")


def b2_key_id() -> str | None:
    return _env("B2_KEY_ID")


def b2_app_key() -> str | None:
    return _env("B2_APP_KEY")


def assets_bucket() -> str | None:
    return _env("B2_ASSETS_BUCKET")


def vault_bucket() -> str | None:
    return _env("B2_VAULT_BUCKET")


def state_bucket() -> str | None:
    return _env("B2_STATE_BUCKET")


# --- Providers --------------------------------------------------------------
# Chat (judge + narration text) runs on Alibaba DashScope. Images run on
# IMAGE_PROVIDER: keyless Pollinations by default, DashScope as failover.

DASHSCOPE_COMPAT_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def dashscope_api_key() -> str | None:
    return _env("DASHSCOPE_API_KEY")


def elevenlabs_api_key() -> str | None:
    return _env("ELEVENLABS_API_KEY")


# --- Tunables (with defaults) ----------------------------------------------

def vault_retention_days() -> int:
    return _env_int("VAULT_RETENTION_DAYS", 7)


def signing_key_path() -> Path:
    raw = _env("SIGNING_KEY_PATH", "data/signing_key.pem")
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


# Image defaults follow IMAGE_PROVIDER. Keyless Pollinations is the default;
# Alibaba DashScope is the paid failover.
_IMAGE_DEFAULTS: dict[str, dict[str, str]] = {
    "pollinations": {"IMAGE_MODEL": "flux", "IMAGE_FALLBACK_MODELS": "turbo"},
    # Cheapest non-pro DashScope line; treat trial credit as scarce.
    "alibaba": {"IMAGE_MODEL": "wan2.7-image", "IMAGE_FALLBACK_MODELS": "qwen-image-2.0"},
}

_IMAGE_PROVIDERS = ("pollinations", "alibaba")


def image_provider_kind() -> str:
    value = (_env("IMAGE_PROVIDER", "pollinations") or "pollinations").strip().lower()
    if value not in _IMAGE_PROVIDERS:
        raise ConfigError(
            f"IMAGE_PROVIDER must be one of {', '.join(_IMAGE_PROVIDERS)}; got {value!r}"
        )
    return value


def image_model() -> str:
    return _env(
        "IMAGE_MODEL", _IMAGE_DEFAULTS[image_provider_kind()]["IMAGE_MODEL"]
    )  # type: ignore[return-value]


def image_fallback_models() -> list[str]:
    raw = (
        _env(
            "IMAGE_FALLBACK_MODELS",
            _IMAGE_DEFAULTS[image_provider_kind()]["IMAGE_FALLBACK_MODELS"],
        )
        or ""
    )
    return [m.strip() for m in raw.split(",") if m.strip()]


def judge_model() -> str:
    # qwen-vl-plus: the cheaper DashScope vision tier; validated live.
    return _env("JUDGE_MODEL", "qwen-vl-plus")  # type: ignore[return-value]


def narration_text_model() -> str:
    return _env("NARRATION_TEXT_MODEL", "qwen3.6-flash")  # type: ignore[return-value]


def chat_fallback_model() -> str | None:
    """Tried once when the primary chat model keeps throttling or erroring.

    qwen-vl-max handles both vision (judge) and plain text (narration)."""
    return _env("CHAT_FALLBACK_MODEL", "qwen-vl-max")


def tts_model() -> str:
    return _env("TTS_MODEL", "eleven_multilingual_v2")  # type: ignore[return-value]


def tts_voice_id() -> str:
    return _env("TTS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")  # type: ignore[return-value]


def judge_threshold() -> int:
    return _env_int("JUDGE_THRESHOLD", 70)


def max_attempts() -> int:
    return _env_int("MAX_ATTEMPTS", 3)


def phash_max_distance() -> int:
    return _env_int("PHASH_MAX_DISTANCE", 10)


def port() -> int:
    return _env_int("PORT", 8000)


def db_path() -> Path:
    raw = _env("LITMUS_DB_PATH", "data/litmus.db")
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


# --- Lazy validation --------------------------------------------------------

_B2_COMMON = ("B2_REGION", "B2_KEY_ID", "B2_APP_KEY")

REQUIRED_BY_SUBSYSTEM: dict[str, tuple[str, ...]] = {
    "b2_assets": _B2_COMMON + ("B2_ASSETS_BUCKET",),
    "b2_vault": _B2_COMMON + ("B2_VAULT_BUCKET",),
    "b2_state": _B2_COMMON + ("B2_STATE_BUCKET",),
    "elevenlabs": ("ELEVENLABS_API_KEY",),
}

def missing_for(subsystem: str) -> list[str]:
    """Return the list of missing env vars for a subsystem (empty when complete)."""
    if subsystem == "ai":
        return [] if _env("DASHSCOPE_API_KEY") is not None else ["DASHSCOPE_API_KEY"]
    names = REQUIRED_BY_SUBSYSTEM.get(subsystem)
    if names is None:
        raise ValueError(f"Unknown subsystem {subsystem!r}")
    return [n for n in names if _env(n) is None]


def require(subsystem: str) -> None:
    """Raise ConfigError naming the missing env vars for a subsystem."""
    missing = missing_for(subsystem)
    if missing:
        raise ConfigError(
            f"{subsystem} is not configured: missing environment variable"
            f"{'s' if len(missing) > 1 else ''} {', '.join(missing)}. "
            f"Set {'them' if len(missing) > 1 else 'it'} in .env (local) or the "
            "deployment's environment variables, then restart."
        )
