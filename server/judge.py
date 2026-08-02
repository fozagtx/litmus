"""The judge — a vision model scoring generated images against the brief.

Implemented as a genblaze ``Evaluator`` so the ``AgentLoop`` drives the
judge-retry cycle. The judge downloads the generated image, sends it to the
vision model with the PRD §8.8 system prompt (verbatim), and parses a strict
JSON verdict.

Failure semantics:
- Pipeline itself failed (no image produced) → EvaluationResult(passed=False,
  metadata.pipeline_failed=True). AgentLoop stops (stop_on_pipeline_failure)
  and the pipeline layer seals an honest failure receipt.
- Judge provider failed (chat call errored, unparseable verdict) → raise.
  The pipeline layer seals an honest failure receipt. The image is NEVER
  silently passed.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx
from genblaze import EvaluationResult, Evaluator
from pydantic import BaseModel, Field

from server import config

logger = logging.getLogger("litmus.judge")

# PRD §8.8 — verbatim. Do not edit.
JUDGE_SYSTEM_PROMPT = """You are a strict art director scoring one generated image against the brief.
Return ONLY JSON: {"score": <0-100>, "reasons": ["<short reason>", ...]}
Score dimensions: subject fidelity to brief (40), composition (25),
technical artifacts (20), style adherence (15).
Under 70 means "reject and retry." Be specific and terse in reasons —
they are fed back into the retry prompt verbatim."""


class JudgeVerdict(BaseModel):
    score: int = Field(ge=0, le=100)
    reasons: list[str]


class JudgeError(RuntimeError):
    """The judge itself failed (provider error or unusable verdict)."""


def download_image(url: str, timeout: float = 60.0) -> tuple[bytes, str]:
    """Fetch image bytes from a remote URL or decode a data: URL.

    Returns (bytes, content_type).
    """
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        media = header[len("data:"):].split(";")[0] or "image/png"
        return base64.b64decode(payload), media
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "image/png").split(";")[0]
    return resp.content, content_type


class LitmusJudge(Evaluator):
    """Vision-model judge. One instance per run — it records every verdict
    (and the downloaded image bytes) so the pipeline layer can seal receipts
    without re-downloading."""

    def __init__(self, brief_prompt: str) -> None:
        self.brief_prompt = brief_prompt
        # Per-iteration records, in evaluation order.
        self.records: list[dict[str, Any]] = []

    def evaluate(self, result) -> EvaluationResult:  # type: ignore[override]
        failed = result.failed_steps()
        if failed or not result.succeeded_steps():
            error = failed[0].error if failed else "no succeeded steps"
            record: dict[str, Any] = {
                "pipeline_failed": True,
                "error": error,
                "image_bytes": None,
                "image_content_type": None,
                "score": None,
                "reasons": [],
            }
            self.records.append(record)
            return EvaluationResult(
                passed=False,
                score=None,
                feedback=f"pipeline failed: {error}",
                metadata={"pipeline_failed": True, "error": error},
            )

        step = result.succeeded_steps()[0]
        if not step.assets:
            raise JudgeError(
                f"Step {step.provider}/{step.model} succeeded but produced no assets"
            )
        asset = step.assets[0]
        image_bytes, content_type = download_image(asset.url)
        if asset.media_type:
            content_type = asset.media_type

        # Record the downloaded image BEFORE scoring: if the judge itself
        # fails, the pipeline layer can still seal an honest generate receipt
        # for the image that exists.
        record: dict[str, Any] = {
            "pipeline_failed": False,
            "error": None,
            "image_bytes": image_bytes,
            "image_content_type": content_type,
            "score": None,
            "reasons": [],
            "judge_error": None,
        }
        self.records.append(record)
        try:
            verdict = self._score(image_bytes, content_type)
        except JudgeError as exc:
            record["judge_error"] = str(exc)
            raise
        threshold = config.judge_threshold()
        passed = verdict.score >= threshold
        record["score"] = verdict.score
        record["reasons"] = verdict.reasons
        return EvaluationResult(
            passed=passed,
            score=verdict.score / 100.0,
            feedback="; ".join(verdict.reasons),
            metadata={"score": verdict.score, "reasons": verdict.reasons},
        )

    def _score(self, image_bytes: bytes, content_type: str) -> JudgeVerdict:
        from genblaze_gmicloud.chat import chat

        data_url = (
            f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        )
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"The brief:\n{self.brief_prompt}",
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        try:
            resp = chat(
                config.judge_model(),
                messages=messages,
                response_format=JudgeVerdict,
                temperature=0,
                timeout=120.0,
            )
        except Exception as exc:
            raise JudgeError(f"Judge model call failed: {exc}") from exc

        text = (resp.text or "").strip()
        try:
            payload = json.loads(_strip_code_fences(text))
            return JudgeVerdict.model_validate(payload)
        except Exception as exc:
            raise JudgeError(
                f"Judge returned an unparseable verdict: {text[:400]!r} ({exc})"
            ) from exc


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
