"""Provider dispatch — one seam between the pipeline and the AI services.

Chat (the vision judge and narration text) runs on Alibaba DashScope via the
OpenAI-wire genblaze helper, using DASHSCOPE_API_KEY. Images run on
IMAGE_PROVIDER:

- "pollinations" (default) → server/pollinations.py, keyless and free
- "alibaba" → server/alibaba.py, DashScope wan/qwen image models

When Pollinations fails a whole run and a DashScope key exists, new runs
fail over to Alibaba for a ten-minute window. ElevenLabs TTS is independent.
Everything here returns real provider objects or raises ConfigError — there
is no mock path.
"""

from __future__ import annotations

import base64
import mimetypes
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from genblaze import ChatMessage, ImageURLContent, ImageURLRef, TextContent

from server import config

# Image providers write generated files to local disk before the pipeline
# fingerprints and uploads them; keep that under data/.
_IMAGE_OUTPUT_DIR = config.PROJECT_ROOT / "data" / "tmp" / "images"


# Sticky cross-provider failover: when the configured image provider fails an
# entire run, runs started in the next window use the fallback provider (an
# Alibaba DashScope key, when configured). Receipts always record the TRUE
# provider from the executed step, so a mid-window label lag on a concurrent
# run cannot corrupt provenance.
_FAILOVER_WINDOW_SEC = 600.0
_failover_until: float = 0.0
_failover_lock = threading.Lock()


def mark_image_provider_failure() -> None:
    """Called when a run dies on image-provider errors; arms the failover."""
    global _failover_until
    if config.image_provider_kind() == "pollinations" and config.dashscope_api_key():
        with _failover_lock:
            _failover_until = time.monotonic() + _FAILOVER_WINDOW_SEC


def effective_image_kind() -> str:
    kind = config.image_provider_kind()
    if kind == "pollinations" and config.dashscope_api_key():
        with _failover_lock:
            if time.monotonic() < _failover_until:
                return "alibaba"
    return kind


def image_provider() -> Any:
    """A fresh image-generation provider instance for the effective kind."""
    kind = effective_image_kind()
    _IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if kind == "pollinations":
        from server.pollinations import PollinationsImageProvider

        return PollinationsImageProvider(output_dir=_IMAGE_OUTPUT_DIR)
    config.require("ai")
    from server.alibaba import AlibabaImageProvider

    return AlibabaImageProvider(
        config.dashscope_api_key() or "", output_dir=_IMAGE_OUTPUT_DIR
    )


_IMAGE_LABELS = {"pollinations": "pollinations", "alibaba": "alibaba-image"}
_IMAGE_DISPLAY = {"pollinations": "Pollinations", "alibaba": "Alibaba Qwen"}


def image_provider_label() -> str:
    """Provider name recorded in receipts/manifests for image generation."""
    return _IMAGE_LABELS[effective_image_kind()]


def image_provider_display() -> str:
    """Human name for step labels and error copy."""
    return _IMAGE_DISPLAY[effective_image_kind()]


def image_model() -> str:
    """The model slug for the effective image provider (failover-aware)."""
    kind = effective_image_kind()
    if kind != config.image_provider_kind():
        return config._IMAGE_DEFAULTS[kind]["IMAGE_MODEL"]
    return config.image_model()


def image_fallback_models() -> list[str]:
    kind = effective_image_kind()
    if kind != config.image_provider_kind():
        raw = config._IMAGE_DEFAULTS[kind]["IMAGE_FALLBACK_MODELS"]
        return [m.strip() for m in raw.split(",") if m.strip()]
    return config.image_fallback_models()


def image_seed_honored() -> bool:
    """Whether the active image provider actually uses a seed param.

    Receipts must not record a seed the model never saw."""
    return effective_image_kind() in ("pollinations", "alibaba")


def chat_provider_label() -> str:
    """Provider name recorded in receipts for judge/narration chat calls."""
    return "alibaba"


def vision_message(text: str, image_data_url: str) -> ChatMessage:
    """A user turn carrying text + an image."""
    return ChatMessage(
        role="user",
        content=[
            TextContent(text=text),
            ImageURLContent(image_url=ImageURLRef(url=image_data_url)),
        ],
    )


def provider_chat(
    model: str,
    *,
    messages: list[ChatMessage] | None = None,
    prompt: str | None = None,
    system: str | None = None,
    temperature: float | None = None,
    force_json: bool = False,
) -> str:
    """Call a DashScope chat model (OpenAI wire); return the response text.

    force_json asks for a JSON-only response via response_mime_type.
    Raises genblaze ProviderError on failure — callers wrap as needed.
    """
    config.require("ai")
    from genblaze import ProviderError
    from genblaze_openai.chat import chat as openai_wire_chat

    kwargs: dict[str, Any] = {}
    if force_json:
        kwargs["response_format"] = {"type": "json_object"}

    def _call(target_model: str) -> str:
        resp = openai_wire_chat(
            target_model,
            messages=messages,
            prompt=prompt,
            system=system,
            temperature=temperature,
            api_key=config.dashscope_api_key(),
            base_url=config.DASHSCOPE_COMPAT_URL,
            timeout=120.0,
            **kwargs,
        )
        return resp.text or ""

    # Retry transient throttling/capacity errors with backoff, then try the
    # fallback model once before giving up honestly.
    attempts = [(model, 0.0), (model, 8.0), (model, 20.0)]
    fallback = config.chat_fallback_model()
    if fallback and fallback != model:
        attempts.append((fallback, 30.0))
    last_exc: Exception | None = None
    for target_model, delay in attempts:
        if delay:
            time.sleep(delay)
        try:
            return _call(target_model)
        except ProviderError as exc:
            text = str(exc)
            if any(k in text for k in ("503", "429", "Throttling", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                last_exc = exc
                continue
            raise
    raise last_exc  # type: ignore[misc]


def read_asset_bytes(url: str, timeout: float = 60.0) -> tuple[bytes, str]:
    """Fetch asset bytes from wherever the provider put them.

    Handles data: URLs (inline), file:// URIs / bare local paths (image and
    TTS providers write to disk), and http(s) URLs. Returns (bytes, content_type).
    """
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        media = header[len("data:"):].split(";")[0] or "application/octet-stream"
        return base64.b64decode(payload), media

    if url.startswith("file://"):
        path = Path(unquote(urlparse(url).path))
    elif "://" not in url:
        path = Path(url)
    else:
        path = None

    if path is not None:
        data = path.read_bytes()
        media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return data, media

    import httpx

    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
    return resp.content, content_type
