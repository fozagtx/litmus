"""The generation pipeline — generate → judge → retry → narrate → seal.

Runs synchronously in a worker thread (max 2 concurrent runs). Every step:
(a) does real work, (b) writes run state to lm-state, (c) seals a signed
receipt to lm-vault with a COMPLIANCE lock at the moment it completes.
Receipts are hash-chained per run via prev_receipt_sha256.

Resume: run_generation consults the persisted internal bookkeeping and skips
already-completed attempts / narration / sealing — sealed receipts and
uploaded attempt assets are never redone.
"""

from __future__ import annotations

import io
import json
import logging
import tempfile
import threading
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image

from server import b2, config, index, providers
from server import runstate as rs
from server.fingerprint import phash64, sha256_hex
from server.judge import JudgeError, LitmusJudge
from server.signing import canonical_bytes, creator_pubkey_field

logger = logging.getLogger("litmus.pipeline")

RUN_SEMAPHORE = threading.BoundedSemaphore(2)

# PRD §8.8 — verbatim. Do not edit.
RETRY_TEMPLATE = """{original_prompt}

Revision notes from art direction (address all):
{judge_reasons_bulleted}"""

NARRATION_TEMPLATE = """Write a single spoken sentence (max 22 words) describing this scene
for a gallery placard, neutral documentary tone: "{original_prompt}\""""

# PRD §8.6 error surfaces.
def provider_down_copy() -> str:
    name = "Google Gemini" if config.ai_provider() == "google" else "GMI Cloud"
    return (
        f"{name} isn't responding. We retried once and logged the failure to "
        "your receipt chain. Try again, or switch providers in options."
    )
ELEVENLABS_DOWN_COPY = (
    "ElevenLabs isn't responding. We logged the failure to your receipt "
    "chain. The image asset was sealed; retry narration with a new run."
)
GENERIC_COPY = (
    "Something failed on our side. Nothing was lost — your vault only ever "
    "gains records, it never loses them."
)


def start_run(run_id: str) -> None:
    threading.Thread(
        target=run_generation, args=(run_id,), daemon=True, name=f"litmus-run-{run_id}"
    ).start()


# --- receipt plumbing -------------------------------------------------------

def _seal_receipt(
    run_id: str,
    internal: dict[str, Any],
    step: str,
    provider: str,
    model: str | None,
    input_sha256: str,
    output_sha256: str,
    detail: dict[str, Any],
) -> tuple[str, str]:
    """Seal one receipt (validated, signed, COMPLIANCE-locked). Returns
    (receipt_key, stored_bytes_sha256). Caller records via rs.mutate."""
    seq = internal.setdefault("seq", 0)
    internal.setdefault("prev_receipt_sha256", None)
    obj = {
        "schema": "litmus/receipt@1",
        "run_id": run_id,
        "seq": seq,
        "step": step,
        "ts_utc": rs.now_utc(),
        "provider": provider,
        "model": model,
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "detail": detail,
        "prev_receipt_sha256": internal["prev_receipt_sha256"],
    }
    key = f"receipts/{run_id}/{seq:03d}-{step}.json"
    _signed, digest = b2.seal_json("vault", key, obj)
    internal["seq"] = seq + 1
    internal["prev_receipt_sha256"] = digest
    return key, digest


def _detail_sha(obj: Any) -> str:
    return sha256_hex(canonical_bytes(obj))


def _retain_until() -> str:
    from datetime import datetime, timedelta, timezone

    return (
        (datetime.now(timezone.utc) + timedelta(days=config.vault_retention_days()))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _make_thumb(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((512, 512), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=82)
        return out.getvalue()


def _bulleted(reasons: list[str]) -> str:
    return "\n".join(f"- {r}" for r in reasons)


def _attempt_prompt(original_prompt: str, attempt: int, prior_reasons: list[str]) -> str:
    if attempt == 0 or not prior_reasons:
        return original_prompt
    return RETRY_TEMPLATE.format(
        original_prompt=original_prompt,
        judge_reasons_bulleted=_bulleted(prior_reasons),
    )


def _step_label(name: str, attempt: int, model: str) -> str:
    if name == "generate":
        provider_display = (
            "Google Gemini" if config.ai_provider() == "google" else "GMI Cloud"
        )
        if attempt == 0:
            return f"Generate image — {provider_display} / {model}"
        retries = f"Retry {attempt} of {config.max_attempts() - 1}"
        # The seed only changes on providers that honor one; don't claim it did.
        if config.ai_provider() == "gmicloud":
            return f"{retries} — seed changed, judge notes applied"
        return f"{retries} — judge notes applied"
    if name == "judge":
        return "Judge — scoring against your prompt"
    if name == "narrate":
        return f"Narrate — ElevenLabs / {model}"
    if name == "seal":
        return "Seal — receipt locked to vault"
    return name


def _add_step(state, internal, name: str, label: str, provider: str | None,
              model: str | None, status: str, detail: dict[str, Any] | None = None):
    from server.schemas import StepState

    step = StepState(
        seq=len(state.steps),
        name=name,
        label=label,
        provider=provider,
        model=model,
        status=status,  # type: ignore[arg-type]
        started_utc=rs.now_utc(),
        detail=detail or {},
    )
    state.steps.append(step)
    return step


def _finish_step(step, status: str, receipt_key: str | None = None,
                 receipt_sha256: str | None = None, detail: dict[str, Any] | None = None):
    step.status = status  # type: ignore[assignment]
    step.ended_utc = rs.now_utc()
    if step.started_utc:
        from datetime import datetime

        try:
            t0 = datetime.fromisoformat(step.started_utc.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(step.ended_utc.replace("Z", "+00:00"))
            step.duration_ms = int((t1 - t0).total_seconds() * 1000)
        except ValueError:
            pass
    if receipt_key:
        step.receipt_key = receipt_key
        step.receipt_sha256 = receipt_sha256
    if detail:
        step.detail = {**step.detail, **detail}


# --- the run ----------------------------------------------------------------

def run_generation(run_id: str) -> None:
    with RUN_SEMAPHORE:
        try:
            _run(run_id)
        except Exception as exc:  # noqa: BLE001 — terminal guard, surfaced honestly
            logger.exception("run %s crashed", run_id)
            _fail_run(run_id, exc)


def _fail_run(run_id: str, exc: Exception) -> None:
    entry = rs.get_entry(run_id)
    if entry is None:
        return
    copy = GENERIC_COPY
    text = str(exc)
    lowered = text.lower()
    if any(k in lowered for k in ("gmi", "gmicloud", "gemini", "google")):
        copy = provider_down_copy()
    elif "elevenlabs" in text.lower():
        copy = ELEVENLABS_DOWN_COPY

    # Seal an honest failure receipt for the crash itself — best effort:
    # if the vault is unreachable this raises and we still mark the run failed.
    try:
        internal = entry.internal
        key, digest = _seal_receipt(
            run_id, internal, "failure", "litmus", None,
            _detail_sha({"run_id": run_id}),
            _detail_sha({"error": text}),
            {"step": "run", "error": text[:2000], "provider": "litmus"},
        )
    except Exception as seal_exc:  # noqa: BLE001
        logger.error("could not seal failure receipt for %s: %s", run_id, seal_exc)
        key = digest = None

    def apply(state, internal):
        state.status = "failed"
        state.error = copy
        for step in state.steps:
            if step.status in ("queued", "running"):
                _finish_step(step, "failed", key, digest, {"error": text[:500]})

    try:
        rs.mutate(run_id, apply)
    except Exception:  # registry gone — nothing more we can do
        logger.exception("could not mark run %s failed", run_id)


def _run(run_id: str) -> None:
    entry = rs.get_entry(run_id) or rs.load_from_state_store(run_id)
    if entry is None:
        raise RuntimeError(f"Run {run_id} not found in registry or lm-state")

    rs.mutate(run_id, lambda s, i: setattr(s, "status", "running"))
    state = entry.state
    internal = entry.internal
    # Defensive defaults for states persisted by an older incarnation.
    import secrets as _secrets

    internal.setdefault("base_seed", _secrets.randbelow(2**31))
    internal.setdefault("seq", 0)
    internal.setdefault("prev_receipt_sha256", None)
    internal.setdefault("narration_done", False)
    internal.setdefault("narration_record", None)
    internal.setdefault("final_sealed", False)
    prompt = state.prompt
    max_attempts = config.max_attempts()

    attempts: list[dict[str, Any]] = internal.setdefault("attempts", [])

    # ---- Phase 1: generate/judge loop (skipped when resumed past it) ----
    need_loop = (
        not internal.get("final_sealed")
        and not any(a.get("passed") for a in attempts)
        and len([a for a in attempts if not a.get("pipeline_failed")]) < max_attempts
        and not any(a.get("pipeline_failed") for a in attempts)
    )
    if need_loop:
        outcome = _generation_loop(run_id, entry, prompt)
        if outcome == "failed":
            return  # state already marked failed with honest receipts

    attempts = internal["attempts"]
    usable = [a for a in attempts if not a.get("pipeline_failed")]
    if not usable:
        raise RuntimeError("No usable generation attempts recorded")
    final = next((a for a in usable if a.get("passed")), usable[-1])
    internal["final_attempt_index"] = attempts.index(final)
    final_asset_id = final["asset_id"]

    # ---- Phase 2: narration (optional) ----
    narration_failed_error: str | None = None
    if state.narration and not internal.get("narration_done"):
        try:
            _narrate(run_id, entry, final)
        except _NarrationError as exc:
            narration_failed_error = str(exc)

    # ---- Phase 3: seal manifests + final receipt ----
    if not internal.get("final_sealed"):
        _seal_all(run_id, entry, final)

    def finish(s, i):
        s.asset_id = final_asset_id
        rec = i.get("narration_record")
        s.audio_asset_id = rec["asset_id"] if rec else None
        if narration_failed_error:
            s.status = "failed"
            s.error = ELEVENLABS_DOWN_COPY
        else:
            s.status = "complete"
            s.error = None

    rs.mutate(run_id, finish)
    logger.info("run %s finished: asset %s", run_id, final_asset_id)


# --- Phase 1: AgentLoop -----------------------------------------------------

def _generation_loop(run_id: str, entry: rs.RunEntry, prompt: str) -> str:
    """Run the generate→judge AgentLoop. Returns "ok" or "failed"."""
    from genblaze import AgentContext, AgentLoop, Modality, Pipeline, StepType

    config.require("ai")
    internal = entry.internal
    state = entry.state
    max_attempts = config.max_attempts()
    attempt_offset = len(internal["attempts"])
    remaining = max_attempts - attempt_offset
    base_seed = internal["base_seed"]

    # Reasons carried over from a previous incarnation (resume mid-retry).
    carried_reasons: list[str] = []
    if attempt_offset and internal["attempts"]:
        carried_reasons = internal["attempts"][-1].get("reasons", [])

    judge = LitmusJudge(prompt)
    provider = providers.image_provider()
    attempt_meta: dict[int, dict[str, Any]] = {}

    def factory(ctx: AgentContext) -> Pipeline:
        attempt = attempt_offset + ctx.iteration
        if ctx.last_evaluation is not None and ctx.last_evaluation.metadata.get("reasons"):
            reasons = list(ctx.last_evaluation.metadata["reasons"])
        elif ctx.iteration == 0:
            reasons = carried_reasons
        else:
            reasons = []
        step_prompt = _attempt_prompt(prompt, attempt, reasons)
        # Only record params the active provider actually honors — a seed in
        # a sealed receipt that the model never saw would be false provenance.
        if config.ai_provider() == "gmicloud":
            seed = base_seed + attempt
            step_params: dict[str, Any] = {"seed": seed, "size": "1024x1024"}
        else:
            seed = None
            step_params = {}
        attempt_meta[attempt] = {"prompt": step_prompt, "seed": seed}
        p = Pipeline("litmus-image", preflight=False)
        p.step(
            provider,
            model=config.image_model(),
            fallback_models=config.image_fallback_models(),
            prompt=step_prompt,
            modality=Modality.IMAGE,
            step_type=StepType.GENERATE,
            params=step_params,
        )
        return p

    loop = AgentLoop(
        factory, judge, max_iterations=remaining, stop_on_pipeline_failure=True
    )

    processed = 0
    try:
        for ev in loop.stream(raise_on_failure=False):
            ev_type = getattr(ev, "type", "")
            if ev_type == "agent.iteration.started":
                attempt = attempt_offset + ev.iteration
                model = config.image_model()

                def add_gen(s, i, attempt=attempt, model=model):
                    _add_step(
                        s, i, "generate", _step_label("generate", attempt, model),
                        providers.image_provider_label(), model, "running", {"attempt": attempt},
                    )

                rs.mutate(run_id, add_gen)
            elif ev_type == "agent.iteration.evaluated":
                attempt = attempt_offset + ev.iteration
                verdict = _process_iteration(
                    run_id, entry, judge, attempt, ev.iteration, ev.result,
                    attempt_meta.get(attempt, {}),
                )
                processed += 1
                if verdict == "pipeline_failed":
                    return "failed"
    except JudgeError as exc:
        _handle_judge_crash(run_id, entry, judge, attempt_offset, attempt_meta, exc)
        return "failed"

    if processed == 0:
        raise RuntimeError("Agent loop produced no iterations")
    return "ok"


def _process_iteration(
    run_id: str,
    entry: rs.RunEntry,
    judge: LitmusJudge,
    attempt: int,
    local_iter: int,
    result,
    meta: dict[str, Any],
) -> str:
    """Fingerprint, upload, and seal receipts for one completed iteration."""
    internal = entry.internal
    rec = judge.records[local_iter]
    prompt_used = meta.get("prompt", entry.state.prompt)
    seed = meta.get("seed", internal["base_seed"] + attempt)

    if rec["pipeline_failed"]:
        error = rec["error"] or "unknown provider failure"
        step_obj = result.run.steps[0] if result.run.steps else None
        provider_name = (step_obj.provider if step_obj else None) or providers.image_provider_label()
        model_name = step_obj.model if step_obj else config.image_model()
        key, digest = _seal_receipt(
            run_id, internal, "failure", provider_name, model_name,
            _detail_sha({"prompt": prompt_used, "params": {"seed": seed, "size": "1024x1024"}}),
            _detail_sha({"error": error}),
            {"step": "generate", "error": error[:2000], "provider": provider_name,
             "attempt": attempt},
        )

        def apply_fail(s, i):
            i["attempts"].append(
                {"attempt": attempt, "pipeline_failed": True, "error": error}
            )
            for st in reversed(s.steps):
                if st.name == "generate" and st.status == "running":
                    _finish_step(st, "failed", key, digest, {"error": error[:500]})
                    break
            s.status = "failed"
            s.error = provider_down_copy()

        rs.mutate(run_id, apply_fail)
        return "pipeline_failed"

    # -- successful generation --
    step_obj = result.succeeded_steps()[0]
    image_bytes: bytes = rec["image_bytes"]
    content_type: str = rec["image_content_type"] or "image/png"
    sha = sha256_hex(image_bytes)
    ph = phash64(image_bytes)
    asset_id = rs.new_asset_id()
    original_key = f"assets/{asset_id}/original.png"
    thumb_key = f"assets/{asset_id}/thumb.webp"
    b2.put_bytes("assets", original_key, image_bytes, content_type)
    b2.put_bytes("assets", thumb_key, _make_thumb(image_bytes), "image/webp")

    gen_key, gen_digest = _seal_receipt(
        run_id, internal, "generate", step_obj.provider or providers.image_provider_label(),
        step_obj.model,
        _detail_sha({"prompt": prompt_used, "params": {"seed": seed, "size": "1024x1024"}}),
        sha,
        {"model": step_obj.model, "provider": step_obj.provider, "seed": seed,
         "attempt": attempt},
    )

    score: int = rec["score"]
    reasons: list[str] = rec["reasons"]
    passed = score >= config.judge_threshold()
    judge_key, judge_digest = _seal_receipt(
        run_id, internal, "judge", providers.chat_provider_label(), config.judge_model(),
        sha,
        _detail_sha({"score": score, "reasons": reasons}),
        {"score": score, "reasons": reasons, "attempt": attempt},
    )

    sdk_manifest_json: str | None = None
    try:
        sdk_manifest_json = result.manifest.to_canonical_json()
    except Exception as exc:  # noqa: BLE001 — SDK manifest is complementary
        logger.warning("could not serialize SDK manifest for %s: %s", asset_id, exc)

    is_last_attempt = attempt >= config.max_attempts() - 1

    def apply_ok(s, i):
        i["attempts"].append(
            {
                "attempt": attempt,
                "pipeline_failed": False,
                "asset_id": asset_id,
                "sha256": sha,
                "phash64": ph,
                "content_type": content_type,
                "prompt_used": prompt_used,
                "seed": seed,
                "model": step_obj.model,
                "provider": step_obj.provider or providers.image_provider_label(),
                "score": score,
                "reasons": reasons,
                "passed": passed,
                "original_key": original_key,
                "thumb_key": thumb_key,
                "created_utc": rs.now_utc(),
                "gen_receipt_key": gen_key,
                "judge_receipt_key": judge_key,
                "sdk_manifest_json": sdk_manifest_json,
            }
        )
        for st in reversed(s.steps):
            if st.name == "generate" and st.status == "running":
                _finish_step(
                    st, "passed" if passed else "discarded", gen_key, gen_digest,
                    {"seed": seed, "model": step_obj.model, "asset_id": asset_id},
                )
                break
        judge_status = "passed" if passed else ("discarded" if is_last_attempt else "retried")
        judge_step = _add_step(
            s, i, "judge", _step_label("judge", attempt, config.judge_model()),
            providers.chat_provider_label(), config.judge_model(), "running", {"attempt": attempt},
        )
        _finish_step(
            judge_step, judge_status, judge_key, judge_digest,
            {"score": score, "reasons": reasons},
        )

    rs.mutate(run_id, apply_ok)
    return "ok"


def _handle_judge_crash(
    run_id: str,
    entry: rs.RunEntry,
    judge: LitmusJudge,
    attempt_offset: int,
    attempt_meta: dict[int, dict[str, Any]],
    exc: JudgeError,
) -> None:
    """The judge itself failed. Seal what we honestly know: the generation
    receipt for the downloaded image (if any) plus a failure receipt."""
    internal = entry.internal
    rec = judge.records[-1] if judge.records else None
    attempt = attempt_offset + (len(judge.records) - 1 if judge.records else 0)
    meta = attempt_meta.get(attempt, {})
    prompt_used = meta.get("prompt", entry.state.prompt)
    seed = meta.get("seed", internal["base_seed"] + attempt)

    if rec is not None and rec.get("judge_error") and rec.get("image_bytes"):
        image_bytes = rec["image_bytes"]
        sha = sha256_hex(image_bytes)
        _seal_receipt(
            run_id, internal, "generate", providers.image_provider_label(), config.image_model(),
            _detail_sha({"prompt": prompt_used, "params": {"seed": seed, "size": "1024x1024"}}),
            sha,
            {"model": config.image_model(), "provider": providers.image_provider_label(),
             "seed": seed, "attempt": attempt, "note": "judge failed after generation"},
        )
        out_sha = sha
    else:
        out_sha = _detail_sha({"error": str(exc)})

    key, digest = _seal_receipt(
        run_id, internal, "failure", providers.chat_provider_label(), config.judge_model(),
        out_sha,
        _detail_sha({"error": str(exc)}),
        {"step": "judge", "error": str(exc)[:2000], "provider": providers.chat_provider_label(),
         "attempt": attempt},
    )

    def apply(s, i):
        for st in reversed(s.steps):
            if st.status == "running":
                _finish_step(st, "failed", key, digest, {"error": str(exc)[:500]})
        s.status = "failed"
        s.error = provider_down_copy()

    rs.mutate(run_id, apply)


# --- Phase 2: narration -----------------------------------------------------

class _NarrationError(RuntimeError):
    pass


def _narrate(run_id: str, entry: rs.RunEntry, final: dict[str, Any]) -> None:
    from genblaze import Modality, Pipeline, StepType
    from genblaze_elevenlabs import ElevenLabsTTSProvider

    config.require("ai")
    config.require("elevenlabs")
    internal = entry.internal
    state = entry.state
    narration_source = state.narration_text or state.prompt

    def add_narrate(s, i):
        _add_step(
            s, i, "narrate", _step_label("narrate", 0, config.tts_model()),
            "elevenlabs-tts", config.tts_model(), "running", {},
        )

    rs.mutate(run_id, add_narrate)

    try:
        sentence = providers.provider_chat(
            config.narration_text_model(),
            prompt=NARRATION_TEMPLATE.format(original_prompt=narration_source),
            temperature=0.4,
        ).strip().strip('"').strip()
        if not sentence:
            raise RuntimeError(
                f"{config.narration_text_model()} returned an empty narration sentence"
            )
    except Exception as exc:
        _narration_failed(run_id, entry, f"narration text generation failed: {exc}",
                          provider=providers.chat_provider_label(), model=config.narration_text_model())
        raise _NarrationError(str(exc)) from exc

    with tempfile.TemporaryDirectory(prefix="litmus-tts-") as tmpdir:
        try:
            p = Pipeline("litmus-tts", preflight=False)
            p.step(
                ElevenLabsTTSProvider(output_dir=tmpdir),
                model=config.tts_model(),
                prompt=sentence,
                modality=Modality.AUDIO,
                step_type=StepType.GENERATE,
                params={"voice_id": config.tts_voice_id()},
            )
            result = p.run(raise_on_failure=False)
            failed = result.failed_steps()
            if failed:
                raise RuntimeError(failed[0].error or "TTS step failed")
            step_obj = result.succeeded_steps()[0]
            if not step_obj.assets:
                raise RuntimeError("TTS step succeeded but produced no audio asset")
            audio_url = step_obj.assets[0].url
            audio_path = unquote(urlparse(audio_url).path) if audio_url.startswith("file:") else audio_url
            with open(audio_path, "rb") as fh:
                audio_bytes = fh.read()
        except Exception as exc:
            _narration_failed(run_id, entry, f"TTS failed: {exc}",
                              provider="elevenlabs-tts", model=config.tts_model())
            raise _NarrationError(str(exc)) from exc

    audio_sha = sha256_hex(audio_bytes)
    audio_asset_id = rs.new_asset_id()
    audio_key = f"assets/{audio_asset_id}/narration.mp3"
    media_type = step_obj.assets[0].media_type or "audio/mpeg"
    b2.put_bytes("assets", audio_key, audio_bytes, media_type)

    key, digest = _seal_receipt(
        run_id, internal, "narrate", "elevenlabs-tts", config.tts_model(),
        _detail_sha({"sentence": sentence, "voice_id": config.tts_voice_id()}),
        audio_sha,
        {"sentence": sentence, "voice_id": config.tts_voice_id(),
         "text_model": config.narration_text_model()},
    )

    def apply(s, i):
        i["narration_record"] = {
            "asset_id": audio_asset_id,
            "sha256": audio_sha,
            "content_type": media_type,
            "sentence": sentence,
            "original_key": audio_key,
            "created_utc": rs.now_utc(),
            "receipt_key": key,
        }
        i["narration_done"] = True
        for st in reversed(s.steps):
            if st.name == "narrate" and st.status == "running":
                _finish_step(st, "passed", key, digest, {"sentence": sentence})
                break

    rs.mutate(run_id, apply)


def _narration_failed(run_id: str, entry: rs.RunEntry, error: str,
                      provider: str, model: str) -> None:
    internal = entry.internal
    key, digest = _seal_receipt(
        run_id, internal, "failure", provider, model,
        _detail_sha({"run_id": run_id, "step": "narrate"}),
        _detail_sha({"error": error}),
        {"step": "narrate", "error": error[:2000], "provider": provider},
    )

    def apply(s, i):
        i["narration_done"] = True
        i["narration_record"] = None
        for st in reversed(s.steps):
            if st.name == "narrate" and st.status == "running":
                _finish_step(st, "failed", key, digest, {"error": error[:500]})
                break

    rs.mutate(run_id, apply)


# --- Phase 3: sealing -------------------------------------------------------

def _manifest_obj(
    asset_id: str,
    kind: str,
    status: str,
    prompt: str,
    provider: str,
    model: str,
    params: dict[str, Any],
    sha256: str,
    phash: str | None,
    media_content_type: str,
    parent_asset: str | None,
    run_id: str,
    created_utc: str,
    retain_until: str,
) -> dict[str, Any]:
    return {
        "schema": "litmus/manifest@1",
        "asset_id": asset_id,
        "created_utc": created_utc,
        "creator_pubkey": creator_pubkey_field(),
        "kind": kind,
        "status": status,
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "params": params,
        "sha256": sha256,
        "phash64": phash,
        "media_content_type": media_content_type,
        "parent_asset": parent_asset,
        "run_id": run_id,
        "retain_until": retain_until,
    }


def _index_row(m: dict[str, Any], manifest_key: str, original_key: str,
               thumb_key: str | None) -> dict[str, Any]:
    return {
        "asset_id": m["asset_id"],
        "kind": m["kind"],
        "status": m["status"],
        "sha256": m["sha256"],
        "phash64": m.get("phash64"),
        "prompt": m["prompt"],
        "provider": m["provider"],
        "model": m["model"],
        "params_json": json.dumps(m["params"], sort_keys=True),
        "created_utc": m["created_utc"],
        "run_id": m["run_id"],
        "parent_asset": m.get("parent_asset"),
        "manifest_key": manifest_key,
        "original_key": original_key,
        "thumb_key": thumb_key,
        "media_content_type": m["media_content_type"],
        "retain_until": m["retain_until"],
        "anchor_batch": None,
    }


def _seal_all(run_id: str, entry: rs.RunEntry, final: dict[str, Any]) -> None:
    internal = entry.internal
    state = entry.state
    retain = _retain_until()
    final_asset_id = final["asset_id"]

    # Final image manifest.
    final_manifest = _manifest_obj(
        final_asset_id, "image", "sealed", final["prompt_used"],
        final["provider"], final["model"],
        {"seed": final["seed"], "size": "1024x1024"},
        final["sha256"], final["phash64"], final["content_type"],
        None, run_id, final["created_utc"], retain,
    )
    manifest_key = f"manifests/{final_asset_id}.json"
    _signed, manifest_digest = b2.seal_json("vault", manifest_key, final_manifest)
    index.upsert_asset(_index_row(final_manifest, manifest_key,
                                  final["original_key"], final["thumb_key"]))

    # Discarded candidates (part of history), linked to the final asset.
    for att in internal["attempts"]:
        if att.get("pipeline_failed") or att["asset_id"] == final_asset_id:
            continue
        m = _manifest_obj(
            att["asset_id"], "image", "discarded", att["prompt_used"],
            att["provider"], att["model"],
            {"seed": att["seed"], "size": "1024x1024"},
            att["sha256"], att["phash64"], att["content_type"],
            final_asset_id, run_id, att["created_utc"], retain,
        )
        k = f"manifests/{att['asset_id']}.json"
        b2.seal_json("vault", k, m)
        index.upsert_asset(_index_row(m, k, att["original_key"], att["thumb_key"]))

    # Audio manifest (if narration succeeded).
    nar = internal.get("narration_record")
    if nar:
        m = _manifest_obj(
            nar["asset_id"], "audio", "sealed", nar["sentence"],
            "elevenlabs-tts", config.tts_model(),
            {"voice_id": config.tts_voice_id()},
            nar["sha256"], None, nar["content_type"],
            final_asset_id, run_id, nar["created_utc"], retain,
        )
        k = f"manifests/{nar['asset_id']}.json"
        b2.seal_json("vault", k, m)
        index.upsert_asset(_index_row(m, k, nar["original_key"], None))

    # SDK manifest for the winning iteration, COMPLIANCE-locked alongside ours.
    sdk_key: str | None = None
    if final.get("sdk_manifest_json"):
        sdk_key = f"sdk-manifests/{final_asset_id}.json"
        b2.backend("vault").put(
            sdk_key,
            final["sdk_manifest_json"].encode("utf-8"),
            content_type="application/json",
            object_lock=b2.vault_lock(),
        )

    # Final seal receipt.
    seal_key, seal_digest = _seal_receipt(
        run_id, internal, "seal", "litmus", None,
        final["sha256"], manifest_digest,
        {"manifest_key": manifest_key, "manifest_sha256": manifest_digest,
         "sdk_manifest_key": sdk_key},
    )

    def apply(s, i):
        i["final_sealed"] = True
        seal_step = _add_step(
            s, i, "seal", _step_label("seal", 0, ""), "litmus", None, "running", {},
        )
        _finish_step(seal_step, "passed", seal_key, seal_digest,
                     {"manifest_key": manifest_key})

    rs.mutate(run_id, apply)


# --- startup resume ---------------------------------------------------------

def resume_incomplete() -> list[str]:
    """Re-enqueue every queued/running run found in lm-state. Returns run ids."""
    rs.load_all_from_state_store()
    resumed = []
    for run_id in rs.incomplete_run_ids():
        logger.info("resuming interrupted run %s", run_id)
        start_run(run_id)
        resumed.append(run_id)
    return resumed
