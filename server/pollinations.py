"""PollinationsImageProvider — free, keyless image generation as a Genblaze provider.

Pollinations (https://image.pollinations.ai) serves FLUX-family image
generation over a plain GET, no API key. This adapter makes it a first-class
Genblaze ``SyncProvider`` so the Litmus pipeline (AgentLoop, receipts,
manifests) treats it exactly like any other provider.

Honored params: ``seed``, ``width``, ``height``. Models: ``flux`` (default)
and ``turbo``. Output is written to a local file, mirroring the
GeminiImageProvider contract (asset.url is a file:// URL until fingerprinted
and uploaded by the pipeline).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import httpx
from genblaze_core._utils import local_file_url
from genblaze_core.exceptions import ProviderError
from genblaze_core.models.asset import Asset
from genblaze_core.models.enums import Modality, ProviderErrorCode
from genblaze_core.models.step import Step
from genblaze_core.providers.base import ProviderCapabilities, SyncProvider
from genblaze_core.providers.family import ModelFamily
from genblaze_core.providers.model_registry import ModelRegistry
from genblaze_core.providers.spec import ModelSpec
from genblaze_core.runnable.config import RunnableConfig

_BASE_URL = "https://image.pollinations.ai/prompt/"
_TIMEOUT_SEC = 180.0

_POLLINATIONS_FAMILY = ModelFamily(
    name="pollinations-image",
    pattern=re.compile(r"^(flux|turbo)$"),
    spec_template=ModelSpec(model_id="*", modality=Modality.IMAGE),
    description="Pollinations free image generation (FLUX family).",
    example_slugs=("flux", "turbo"),
)

_FALLBACK = ModelSpec(model_id="*", modality=Modality.IMAGE)


def _map_status(code: int) -> ProviderErrorCode:
    if code == 429:
        return ProviderErrorCode.RATE_LIMIT
    if code in (401, 403):
        return ProviderErrorCode.AUTH_FAILURE
    if code >= 500:
        return ProviderErrorCode.SERVER_ERROR
    return ProviderErrorCode.INVALID_INPUT


class PollinationsImageProvider(SyncProvider):
    """Provider adapter for Pollinations' keyless image endpoint.

    Args:
        output_dir: Directory for output image files (required by Litmus so
            the pipeline can fingerprint the exact bytes).
        http_timeout: Per-request timeout; generation can take a minute.
    """

    name = "pollinations"

    def __init__(
        self,
        *,
        output_dir: str | Path,
        http_timeout: float = _TIMEOUT_SEC,
        models: ModelRegistry | None = None,
    ) -> None:
        super().__init__(models=models)
        self._output_dir = Path(output_dir)
        self._http_timeout = http_timeout

    @classmethod
    def create_registry(cls) -> ModelRegistry:
        return ModelRegistry(provider_families=(_POLLINATIONS_FAMILY,), fallback=_FALLBACK)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supported_modalities=[Modality.IMAGE],
            supported_inputs=["text"],
            models=self._models.known(),
            output_formats=["image/jpeg", "image/png"],
        )

    def generate(self, step: Step, config: RunnableConfig | None = None) -> Step:
        prompt = step.prompt or ""
        if not prompt.strip():
            raise ProviderError(
                "Pollinations requires a non-empty prompt",
                error_code=ProviderErrorCode.INVALID_INPUT,
            )
        params: dict[str, str] = {
            "model": step.model,
            "width": str(step.params.get("width", 1024)),
            "height": str(step.params.get("height", 1024)),
            "nologo": "true",
        }
        if step.params.get("seed") is not None:
            params["seed"] = str(step.params["seed"])

        url = _BASE_URL + quote(prompt, safe="")
        try:
            resp = httpx.get(
                url, params=params, timeout=self._http_timeout, follow_redirects=True
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Pollinations timed out after {self._http_timeout:.0f}s",
                error_code=ProviderErrorCode.TIMEOUT,
            ) from exc
        except Exception as exc:
            raise ProviderError(
                f"Pollinations request failed: {exc}",
                error_code=ProviderErrorCode.SERVER_ERROR,
            ) from exc

        if resp.status_code != 200:
            raise ProviderError(
                f"Pollinations returned HTTP {resp.status_code}: {resp.text[:200]}",
                error_code=_map_status(resp.status_code),
            )
        content_type = resp.headers.get("content-type", "").split(";")[0].strip()
        if not content_type.startswith("image/"):
            raise ProviderError(
                f"Pollinations returned non-image content ({content_type or 'unknown'})",
                error_code=ProviderErrorCode.SERVER_ERROR,
            )
        if len(resp.content) < 1024:
            raise ProviderError(
                f"Pollinations returned a suspiciously small body ({len(resp.content)} bytes)",
                error_code=ProviderErrorCode.SERVER_ERROR,
            )

        suffix = ".png" if content_type == "image/png" else ".jpg"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / f"{step.step_id}{suffix}"
        out_path.write_bytes(resp.content)
        step.assets.append(
            Asset(url=local_file_url(out_path.resolve()), media_type=content_type)
        )
        step.provider_payload = {
            "pollinations": {"status": resp.status_code, "bytes": len(resp.content)}
        }
        return step
