"""Provider dispatch — one seam between the pipeline and the AI stack.

AI_PROVIDER selects the inference stack for image generation, the vision
judge, and narration text:

- "google"   → Gemini via genblaze-google (GEMINI_API_KEY; free-tier friendly)
- "gmicloud" → GMI Cloud via genblaze-gmicloud (GMI_API_KEY; hackathon credits)

ElevenLabs TTS is provider-independent and stays as-is. Everything here
returns real provider objects or raises ConfigError — there is no mock path.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from genblaze import ChatMessage, ImageURLContent, ImageURLRef, TextContent

from server import config

# Gemini writes generated images to local disk (unlike GMI's remote queue
# URLs), so give it a directory we control under data/.
_IMAGE_OUTPUT_DIR = config.PROJECT_ROOT / "data" / "tmp" / "images"


def image_provider() -> Any:
    """A fresh image-generation provider instance for the active stack."""
    config.require("ai")
    if config.ai_provider() == "google":
        from genblaze_google.gemini_image import GeminiImageProvider

        _IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return GeminiImageProvider(output_dir=_IMAGE_OUTPUT_DIR)
    from genblaze_gmicloud.image import GMICloudImageProvider

    return GMICloudImageProvider()


def image_provider_label() -> str:
    """Provider name recorded in receipts/manifests for image generation."""
    return "google-gemini-image" if config.ai_provider() == "google" else "gmicloud-image"


def chat_provider_label() -> str:
    """Provider name recorded in receipts for judge/narration chat calls."""
    return "google" if config.ai_provider() == "google" else "gmicloud"


def vision_message(text: str, image_data_url: str) -> ChatMessage:
    """A user turn carrying text + an image, portable across both stacks."""
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
    response_format: Any = None,
) -> str:
    """Call the active stack's chat model; return the response text.

    force_json asks the provider for a JSON-only response using whichever
    mechanism it supports (Gemini: response_mime_type; GMI: response_format).
    Raises genblaze ProviderError on failure — callers wrap as needed.
    """
    config.require("ai")
    if config.ai_provider() == "google":
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

    from genblaze_gmicloud.chat import chat as gmi_chat

    resp = gmi_chat(
        model,
        messages=messages,
        prompt=prompt,
        system=system,
        temperature=temperature,
        response_format=response_format if force_json else None,
        timeout=120.0,
    )
    return resp.text or ""


def read_asset_bytes(url: str, timeout: float = 60.0) -> tuple[bytes, str]:
    """Fetch asset bytes from wherever the provider put them.

    Handles the three shapes genblaze providers actually produce:
    data: URLs (inline), file:// URIs / bare local paths (Gemini image,
    ElevenLabs audio), and http(s) URLs (GMI request queue).
    Returns (bytes, content_type).
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
