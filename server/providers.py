"""Provider dispatch — one seam between the pipeline and the AI services.

Chat (the vision judge and narration text) runs on Gemini via genblaze-google,
using GEMINI_API_KEY. Images run on IMAGE_PROVIDER:

- "pollinations" (default) → server/pollinations.py, keyless and free
- "google" → Gemini image models, requires billing enabled on the key

ElevenLabs TTS is independent of both. Everything here returns real provider
objects or raises ConfigError — there is no mock path.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from genblaze import ChatMessage, ImageURLContent, ImageURLRef, TextContent

from server import config

# Image providers write generated files to local disk before the pipeline
# fingerprints and uploads them; keep that under data/.
_IMAGE_OUTPUT_DIR = config.PROJECT_ROOT / "data" / "tmp" / "images"


def image_provider() -> Any:
    """A fresh image-generation provider instance for IMAGE_PROVIDER."""
    kind = config.image_provider_kind()
    _IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if kind == "pollinations":
        from server.pollinations import PollinationsImageProvider

        return PollinationsImageProvider(output_dir=_IMAGE_OUTPUT_DIR)
    config.require("ai")
    from genblaze_google.gemini_image import GeminiImageProvider

    return GeminiImageProvider(output_dir=_IMAGE_OUTPUT_DIR)


_IMAGE_LABELS = {"pollinations": "pollinations", "google": "google-gemini-image"}
_IMAGE_DISPLAY = {"pollinations": "Pollinations", "google": "Google Gemini"}


def image_provider_label() -> str:
    """Provider name recorded in receipts/manifests for image generation."""
    return _IMAGE_LABELS[config.image_provider_kind()]


def image_provider_display() -> str:
    """Human name for step labels and error copy."""
    return _IMAGE_DISPLAY[config.image_provider_kind()]


def image_seed_honored() -> bool:
    """Whether the active image provider actually uses a seed param.

    Receipts must not record a seed the model never saw."""
    return config.image_provider_kind() == "pollinations"


def chat_provider_label() -> str:
    """Provider name recorded in receipts for judge/narration chat calls."""
    return "google"


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
    """Call a Gemini chat model; return the response text.

    force_json asks for a JSON-only response via response_mime_type.
    Raises genblaze ProviderError on failure — callers wrap as needed.
    """
    config.require("ai")
    from genblaze_google.chat import chat as google_chat

    kwargs: dict[str, Any] = {}
    if force_json:
        # Merged into generation_config by genblaze-google.
        kwargs["response_mime_type"] = "application/json"
    resp = google_chat(
        model,
        messages=messages,
        prompt=prompt,
        system=system,
        temperature=temperature,
        **kwargs,
    )
    return resp.text or ""


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
