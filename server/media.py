"""Media serving — streams originals, thumbnails and narration from lm-assets."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from server import b2, index
from server.config import ConfigError

router = APIRouter()

_ALLOWED_NAMES = {"original.png", "thumb.webp", "narration.mp3"}

_FALLBACK_TYPES = {
    "original.png": "image/png",
    "thumb.webp": "image/webp",
    "narration.mp3": "audio/mpeg",
}


@router.get("/api/media/{asset_id}/{name}")
def get_media(asset_id: str, name: str):
    if name not in _ALLOWED_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown media name {name!r}")
    row = index.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset {asset_id!r}")

    key = f"assets/{asset_id}/{name}"
    if name == "original.png":
        if row["kind"] != "image":
            raise HTTPException(status_code=404, detail="Asset has no image original")
        content_type = row["media_content_type"] or _FALLBACK_TYPES[name]
    elif name == "thumb.webp":
        if not row.get("thumb_key"):
            raise HTTPException(status_code=404, detail="Asset has no thumbnail")
        content_type = _FALLBACK_TYPES[name]
    else:  # narration.mp3
        if row["kind"] != "audio":
            raise HTTPException(status_code=404, detail="Asset has no narration audio")
        content_type = row["media_content_type"] or _FALLBACK_TYPES[name]

    try:
        if not b2.exists("assets", key):
            raise HTTPException(status_code=404, detail=f"Media object {key!r} not found")
        stream = b2.stream("assets", key)
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Storage read failed: {exc}") from exc

    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
