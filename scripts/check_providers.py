#!/usr/bin/env python3
"""Validate the configured models against the LIVE provider catalogs.

Requires GEMINI_API_KEY plus ELEVENLABS_API_KEY. Checks:
  - IMAGE_MODEL + IMAGE_FALLBACK_MODELS via the provider's validate_model
  - JUDGE_MODEL and NARRATION_TEXT_MODEL via a 1-token chat ping
  - TTS_MODEL via ElevenLabs catalog discovery / validate_model

Use this to discover valid model slugs when the defaults are off.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import config  # noqa: E402
from server.config import ConfigError  # noqa: E402

ROWS: list[tuple[str, str, str, str]] = []  # (role, model, status, detail)


def add(role: str, model: str, ok: bool | None, detail: str) -> None:
    status = {True: "OK", False: "FAIL", None: "WARN"}[ok]
    ROWS.append((role, model, status, detail))


def check_image_models() -> None:
    from server import providers as litmus_providers

    provider = litmus_providers.image_provider()
    models = [config.image_model()] + config.image_fallback_models()
    roles = ["IMAGE_MODEL"] + [
        f"IMAGE_FALLBACK_MODELS[{i}]" for i in range(len(models) - 1)
    ]
    for role, model in zip(roles, models):
        try:
            result = provider.validate_model(model)
            outcome = result.outcome.value
            if result.is_terminal_failure:
                hint = ""
                if result.suggested_slugs:
                    hint = f" — did you mean: {', '.join(result.suggested_slugs)}?"
                add(role, model, False, f"{outcome}: {result.detail or 'not found'}{hint}")
            elif outcome == "ok_authoritative":
                add(role, model, True, "confirmed by provider catalog")
            else:
                add(role, model, None, f"{outcome}: {result.detail or 'passes through to upstream'}")
        except Exception as exc:  # noqa: BLE001
            add(role, model, False, str(exc))


def check_chat_model(role: str, model: str) -> None:
    from server import providers as litmus_providers

    try:
        litmus_providers.provider_chat(model, prompt="ping")
        add(role, model, True, "chat ping ok")
    except Exception as exc:  # noqa: BLE001
        add(role, model, False, str(exc))


def check_tts_model() -> None:
    from genblaze_elevenlabs import ElevenLabsTTSProvider

    model = config.tts_model()
    try:
        provider = ElevenLabsTTSProvider()
        discovery = provider.discover_models()
        result = provider.validate_model(model)
        if result.is_ok:
            add("TTS_MODEL", model, True, f"validated ({result.outcome.value})")
        else:
            known = ", ".join(sorted(discovery.models)[:8]) if discovery.models else "none listed"
            add("TTS_MODEL", model, False,
                f"{result.outcome.value}: {result.detail or 'unknown'} — catalog has: {known}")
    except Exception as exc:  # noqa: BLE001
        add("TTS_MODEL", model, False, str(exc))


def main() -> int:
    hard_fail = False
    provider_label = "GEMINI"
    try:
        config.require("ai")
        check_image_models()
        check_chat_model("JUDGE_MODEL", config.judge_model())
        check_chat_model("NARRATION_TEXT_MODEL", config.narration_text_model())
    except ConfigError as exc:
        add(provider_label, "-", False, str(exc))
        hard_fail = True

    try:
        config.require("elevenlabs")
        check_tts_model()
    except ConfigError as exc:
        add("ELEVENLABS", "-", False, str(exc))
        hard_fail = True

    w_role = max(len(r[0]) for r in ROWS)
    w_model = max(len(r[1]) for r in ROWS)
    print(f"\n{'ROLE'.ljust(w_role)}  {'MODEL'.ljust(w_model)}  STATUS  DETAIL")
    print("-" * (w_role + w_model + 60))
    for role, model, status, detail in ROWS:
        print(f"{role.ljust(w_role)}  {model.ljust(w_model)}  {status.ljust(6)}  {detail}")

    failed = hard_fail or any(r[2] == "FAIL" for r in ROWS)
    print()
    if failed:
        print("One or more checks FAILED. Fix the model slugs or keys before generating.")
        return 1
    if any(r[2] == "WARN" for r in ROWS):
        print("All hard checks passed. WARN rows pass through to the provider unverified.")
    else:
        print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
