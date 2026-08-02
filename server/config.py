"""Configuration for the Litmus backend.

All values are read from environment variables (loaded from the project-root
.env via python-dotenv). Importing this module NEVER raises on missing
credentials — validation is lazy, per subsystem, via :func:`require` so that
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

_AI_PROVIDERS = ("google", "gmicloud")


def ai_provider() -> str:
    """Which inference stack powers image gen + judge + narration text.

    "google" (Gemini, default — free-tier API key from AI Studio) or
    "gmicloud" (the hackathon partner cloud, needs GMI credits).
    """
    value = (_env("AI_PROVIDER", "google") or "google").strip().lower()
    if value not in _AI_PROVIDERS:
        raise ConfigError(
            f"AI_PROVIDER must be one of {', '.join(_AI_PROVIDERS)}; got {value!r}"
        )
    return value


def gmi_api_key() -> str | None:
    return _env("GMI_API_KEY")


def gemini_api_key() -> str | None:
    return _env("GEMINI_API_KEY")


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


_MODEL_DEFAULTS: dict[str, dict[str, str]] = {
    "google": {
        # 2.5-generation models 404 for accounts created after the 3.x
        # rollout; these are the current stable slugs (scripts/check_providers.py
        # validates against the live catalog).
        "IMAGE_MODEL": "gemini-3.1-flash-image",
        "IMAGE_FALLBACK_MODELS": "gemini-2.5-flash-image",
        "JUDGE_MODEL": "gemini-3.6-flash",
        "NARRATION_TEXT_MODEL": "gemini-3.6-flash",
    },
    "gmicloud": {
        "IMAGE_MODEL": "seedream-4-0",
        "IMAGE_FALLBACK_MODELS": "flux-kontext-pro",
        "JUDGE_MODEL": "Qwen/Qwen2.5-VL-72B-Instruct",
        "NARRATION_TEXT_MODEL": "deepseek-ai/DeepSeek-V3",
    },
}


def _model_default(name: str) -> str:
    return _MODEL_DEFAULTS[ai_provider()][name]


def image_model() -> str:
    return _env("IMAGE_MODEL", _model_default("IMAGE_MODEL"))  # type: ignore[return-value]


def image_fallback_models() -> list[str]:
    raw = _env("IMAGE_FALLBACK_MODELS", _model_default("IMAGE_FALLBACK_MODELS")) or ""
    return [m.strip() for m in raw.split(",") if m.strip()]


def judge_model() -> str:
    return _env("JUDGE_MODEL", _model_default("JUDGE_MODEL"))  # type: ignore[return-value]


def narration_text_model() -> str:
    return _env(
        "NARRATION_TEXT_MODEL", _model_default("NARRATION_TEXT_MODEL")
    )  # type: ignore[return-value]


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

_AI_KEY_BY_PROVIDER = {"google": "GEMINI_API_KEY", "gmicloud": "GMI_API_KEY"}


def ai_key_env() -> str:
    """The API-key env var name for the active AI_PROVIDER."""
    return _AI_KEY_BY_PROVIDER[ai_provider()]


def missing_for(subsystem: str) -> list[str]:
    """Return the list of missing env vars for a subsystem (empty when complete)."""
    if subsystem == "ai":
        # Resolved dynamically: which key is required depends on AI_PROVIDER.
        return [] if _env(ai_key_env()) is not None else [ai_key_env()]
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
