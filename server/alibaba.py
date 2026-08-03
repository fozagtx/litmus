"""AlibabaImageProvider · DashScope (Model Studio intl) image generation.

Fallback image provider behind Pollinations. Uses the cheapest non-pro line
(wan2.7-image by default) through DashScope's native async task API, verified
against the live service:

  submit:  POST /api/v1/services/aigc/image-generation/generation
           headers: Authorization Bearer, X-DashScope-Async: enable
           body:    {model, input: {messages: [{role, content: [{text}]}]},
                     parameters: {size: "W*H", n: 1, seed}}
  poll:    GET /api/v1/tasks/{task_id} → task_status
  result:  choices[0].message.content[*].image → presigned URL (also accepts
           the results[].url shape some model families return)

Constraint: total pixels must be within [589824, 16777216] (768x768 minimum).
Output is downloaded and written to a local file, mirroring the other image
providers so the pipeline fingerprints exact bytes.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

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

_BASE = "https://dashscope-intl.aliyuncs.com/api/v1"
_POLL_INTERVAL = 4.0
_MAX_WAIT_SEC = 300.0

_ALIBABA_FAMILY = ModelFamily(
    name="alibaba-image",
    pattern=re.compile(r"^(wan|qwen-image)"),
    spec_template=ModelSpec(model_id="*", modality=Modality.IMAGE),
    description="DashScope image generation (wan / qwen-image families).",
    example_slugs=("wan2.7-image", "qwen-image-2.0"),
)

_FALLBACK = ModelSpec(model_id="*", modality=Modality.IMAGE)


def _map_code(status: int, code: str) -> ProviderErrorCode:
    if status == 429 or "Throttling" in code or "quota" in code.lower():
        return ProviderErrorCode.RATE_LIMIT
    if status in (401, 403):
        return ProviderErrorCode.AUTH_FAILURE
    if status >= 500:
        return ProviderErrorCode.SERVER_ERROR
    return ProviderErrorCode.INVALID_INPUT


class AlibabaImageProvider(SyncProvider):
    """Provider adapter for DashScope's async image-generation task API."""

    name = "alibaba-image"

    def __init__(
        self,
        api_key: str,
        *,
        output_dir: str | Path,
        models: ModelRegistry | None = None,
    ) -> None:
        super().__init__(models=models)
        if not api_key:
            raise ProviderError(
                "DASHSCOPE_API_KEY is not set",
                error_code=ProviderErrorCode.AUTH_FAILURE,
            )
        self._api_key = api_key
        self._output_dir = Path(output_dir)

    @classmethod
    def create_registry(cls) -> ModelRegistry:
        return ModelRegistry(provider_families=(_ALIBABA_FAMILY,), fallback=_FALLBACK)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supported_modalities=[Modality.IMAGE],
            supported_inputs=["text"],
            models=self._models.known(),
            output_formats=["image/png", "image/jpeg"],
        )

    def generate(self, step: Step, config: RunnableConfig | None = None) -> Step:
        prompt = (step.prompt or "").strip()
        if not prompt:
            raise ProviderError(
                "Alibaba image generation requires a non-empty prompt",
                error_code=ProviderErrorCode.INVALID_INPUT,
            )
        width = int(step.params.get("width", 1024))
        height = int(step.params.get("height", 1024))
        params: dict = {"size": f"{width}*{height}", "n": 1}
        seed = step.params.get("seed", step.seed)
        if seed is not None:
            params["seed"] = int(seed) % 2147483647

        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = httpx.post(
            f"{_BASE}/services/aigc/image-generation/generation",
            headers={**headers, "X-DashScope-Async": "enable"},
            json={
                "model": step.model,
                "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                "parameters": params,
            },
            timeout=30.0,
        )
        if resp.status_code != 200:
            body = resp.json() if "json" in resp.headers.get("content-type", "") else {}
            raise ProviderError(
                f"DashScope submit failed ({resp.status_code}): "
                f"{body.get('code', '')} {body.get('message', resp.text[:200])}",
                error_code=_map_code(resp.status_code, str(body.get("code", ""))),
            )
        task_id = resp.json()["output"]["task_id"]
        step.metadata["upstream_id"] = task_id

        deadline = time.monotonic() + _MAX_WAIT_SEC
        while True:
            if time.monotonic() > deadline:
                raise ProviderError(
                    f"DashScope task {task_id} did not finish within {_MAX_WAIT_SEC:.0f}s",
                    error_code=ProviderErrorCode.TIMEOUT,
                )
            time.sleep(_POLL_INTERVAL)
            out = (
                httpx.get(f"{_BASE}/tasks/{task_id}", headers=headers, timeout=20.0)
                .json()
                .get("output", {})
            )
            status = out.get("task_status", "")
            if status == "SUCCEEDED":
                break
            if status in ("FAILED", "CANCELED"):
                raise ProviderError(
                    f"DashScope task {status}: {out.get('code', '')} "
                    f"{out.get('message', '')}",
                    error_code=_map_code(400, str(out.get("code", ""))),
                )

        url = None
        for choice in out.get("choices") or []:
            for part in choice.get("message", {}).get("content", []) or []:
                url = part.get("image") or url
        for res in out.get("results") or []:
            url = res.get("url") or url
        if not url:
            raise ProviderError(
                "DashScope task succeeded but returned no image URL",
                error_code=ProviderErrorCode.SERVER_ERROR,
            )

        img = httpx.get(url, timeout=120.0)
        if img.status_code != 200 or not img.headers.get("content-type", "").startswith("image/"):
            raise ProviderError(
                f"DashScope image download failed ({img.status_code})",
                error_code=ProviderErrorCode.SERVER_ERROR,
            )
        content_type = img.headers["content-type"].split(";")[0]
        suffix = ".png" if content_type == "image/png" else ".jpg"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / f"{step.step_id}{suffix}"
        out_path.write_bytes(img.content)
        step.assets.append(
            Asset(url=local_file_url(out_path.resolve()), media_type=content_type)
        )
        step.provider_payload = {"dashscope": {"task_id": task_id, "bytes": len(img.content)}}
        return step
