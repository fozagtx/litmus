# Litmus

**Your creative memory, tested and sealed.**

Litmus is a generation studio where every AI asset is born with a signed birth
certificate — stored in write-once vault storage that nobody can rewrite. Not
us. Not anyone. Verification works even on a cropped, re-compressed screenshot.

Built for the Backblaze Generative Media Hackathon on **Backblaze B2 Object
Lock** and the **Genblaze** pipeline SDK.

## How it works

1. **Born verifiable.** Every generation gets a signed JSON manifest (prompt,
   model, provider, params, parent asset, timestamps, creator key) at the
   moment of creation. Manifests and per-step receipts are Ed25519-signed.
2. **Sealed, not stored.** Manifests, receipts, and hourly Merkle anchors are
   written to a B2 bucket with **Object Lock in compliance mode** —
   write-once-read-many. Not the operator, not a hacker with the keys, not
   Backblaze support can alter or delete them until retention expires.
3. **Recoverable from abuse.** Alongside SHA-256, every image gets a
   perceptual hash. The public verify page accepts a cropped, re-compressed,
   screenshotted copy and still resurrects its full birth certificate via
   Hamming-distance lookup.
4. **The pipeline is the audit trail.** Genblaze orchestrates
   generate → judge → retry → narrate → seal across the configured AI stack
   (Google Gemini by default, GMI Cloud selectable) and ElevenLabs.
   Every step — including the attempts the judge rejected — is a signed,
   locked receipt. The vault remembers what the pipeline *didn't* choose,
   and why.
5. **Exportable.** One click produces a signed archive of the entire vault —
   assets, manifests, receipts, Merkle proofs, and an offline `verify.py`
   that checks all of it without this service existing.

## Stack

- **Backend:** Python 3.11, FastAPI, Genblaze SDK
  (`genblaze[google,gmicloud,elevenlabs]`), boto3 against B2's S3-compatible
  API, `imagehash`, `cryptography` (Ed25519), SQLite for the fingerprint index.
- **AI providers:** `AI_PROVIDER=google` (default) runs image generation, the
  vision judge, and narration text on Gemini — a free AI Studio key works.
  `AI_PROVIDER=gmicloud` switches all three to GMI Cloud. ElevenLabs narrates
  either way (free tier is enough).
- **Frontend:** Vite + React + TypeScript, Tailwind. Signatures and Merkle
  inclusion proofs are re-verified **in the browser** — don't trust the
  server, check the math yourself.
- **Storage:** three B2 buckets — `assets` (media + thumbnails), `vault`
  (Object Lock COMPLIANCE: manifests, receipts, anchors), `state` (resumable
  run state, exports).

## Setup from zero

```bash
# 0. Accounts: Backblaze B2 + ElevenLabs (free tier) + a Gemini API key
#    (free at https://aistudio.google.com/apikey). Create a B2 application key.

# 1. Python env
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt

# 2. Configure
cp .env.example .env      # fill in B2 + provider keys, pick bucket names

# 3. Keys and buckets
python scripts/gen_keys.py          # Ed25519 signing keypair
python scripts/create_buckets.py    # creates buckets; vault gets Object Lock
                                    # (COMPLIANCE) at creation — irreversible
python scripts/check_providers.py   # validates your model slugs against the
                                    # live GMI / ElevenLabs catalogs

# 4. Run
uvicorn server.main:app --port 8000
cd web && npm install && npm run dev   # dev UI on :5173, proxies /api to :8000

# Production: npm run build, then the FastAPI server serves web/dist itself.
```

Docker: `docker build -t litmus . && docker run --env-file .env -p 8000:8000 litmus`

## Verifying without us

Every export zip contains `verify.py`. Offline, it re-hashes every asset,
checks every Ed25519 signature, re-links every receipt chain, and recomputes
every Merkle root against the sealed anchors:

```bash
python verify.py            # → N/N records verified
```

## Honest limitations

- **Compliance lock is irreversible.** A bug that writes garbage to the vault
  means garbage locked for the retention period. We schema-validate before
  every locked write and run 7-day retention for the demo; production should
  use 365+ days and a governance-mode staging bucket.
- **Perceptual hashing has limits.** Heavy crops (>60%), mirrors, and
  rotations can defeat pHash; distinct-but-similar images can collide at loose
  thresholds. The threshold is conservative (≤10/64 bits), matches are
  reported with a similarity percentage rather than a binary yes, and the
  bit-for-bit claim is only ever made on an exact SHA-256 + signature match.
- **The trust root is the service signing key.** v1 proves *this service*
  sealed a record at time T — tamper-evident notarization, not identity
  attestation of the human behind the account. Per-user keys are schema'd
  (`creator_pubkey`) and on the roadmap.
- **Absence isn't evidence.** "No record found" never means "this file is
  fake" — only that it wasn't sealed here. The UI copy enforces this.
- **Merkle anchoring is operator-computed.** Locked receipts make retroactive
  edits impossible, but pre-seal manipulation is a trust gap until roots are
  published externally (a public transparency log is the roadmap fix).
- **Public verify endpoint.** Uploads are capped at 25 MB, rate-limited by
  IP, and never stored.
- **Prompts are public.** Manifests are designed to be shown to verifiers;
  anyone who verifies an asset can read its prompt. The studio says so before
  you generate.

## Roadmap

Style capsules (generate with someone's creative memory, provenance-credited) →
C2PA embedding + per-user keys → video pipeline + embedding-based verify at
scale → team vaults with Event-Notification-driven auto-sealing.
