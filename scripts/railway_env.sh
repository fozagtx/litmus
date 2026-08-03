#!/usr/bin/env bash
# Push Litmus runtime env vars from .env to the linked Railway service.
# Skips empty values. The master B2 key is deliberately NOT pushed —
# the server never uses it. SIGNING_KEY_B64 is derived from the local PEM.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo ".env not found — run scripts/bootstrap_b2.py first"; exit 1; }
[ -f data/signing_key.pem ] || { echo "data/signing_key.pem not found — run scripts/gen_keys.py"; exit 1; }

# shellcheck disable=SC1091
set -a; source .env; set +a

ARGS=()
add() { local v="${!1:-}"; [ -n "$v" ] && ARGS+=(--set "$1=$v") || echo "skipping empty $1"; }

for name in B2_REGION B2_KEY_ID B2_APP_KEY B2_ASSETS_BUCKET B2_VAULT_BUCKET \
            B2_STATE_BUCKET DASHSCOPE_API_KEY IMAGE_PROVIDER \
            ELEVENLABS_API_KEY VAULT_RETENTION_DAYS IMAGE_MODEL \
            IMAGE_FALLBACK_MODELS JUDGE_MODEL NARRATION_TEXT_MODEL \
            TTS_MODEL TTS_VOICE_ID JUDGE_THRESHOLD MAX_ATTEMPTS CHAT_FALLBACK_MODEL; do
  add "$name"
done

SIGNING_KEY_B64="$(base64 < data/signing_key.pem | tr -d '\n')"
ARGS+=(--set "SIGNING_KEY_B64=$SIGNING_KEY_B64")

railway variables "${ARGS[@]}"
echo "variables pushed — Railway will redeploy the service"
