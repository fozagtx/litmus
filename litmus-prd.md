# Litmus — Product Requirements Document

**Version:** 1.1 (Hackathon build — renamed to Litmus)
**Date:** August 2, 2026
**Target:** Backblaze Generative Media Hackathon — deadline Aug 3, 2026, 9:00 PM GMT
**Author:** Solo build / small team
**Status:** Locked for build. No scope additions after this document.

---

## 0. One-liner

> **Litmus — your creative memory, tested and sealed.** Every AI generation you make is stored, signed, and sealed in a tamper-proof vault you own. Export it. Prove it. Nobody — including us — can rewrite your creative history.

**Elevator pitch (30 seconds):**
"Every AI image and audio clip you generate today is a receipt-less orphan. Screenshot it and its history is gone; the platform that made it can delete or alter its record at will. Litmus is a generation studio where every asset is born with a signed birth certificate, sealed in write-once storage that even we can't modify, and recoverable even from a cropped screenshot. The 0G hackathon winners proved 'memory as an asset' wins with a blockchain. We built it with a $6/TB storage bucket."

---

## 1. Problem statement

1. **Provenance dies at the first screenshot.** Metadata-based provenance (C2PA, EXIF) is stripped by every re-encode, crop, and messaging app. The moment media leaves the generator, its history is gone.
2. **Creators don't own their generation history.** It lives in a SaaS database that can be edited, purged, or shut down. There is no export, no proof, no portability.
3. **AI pipelines are unauditable.** When a multi-step pipeline (generate → judge → retry → composite) produces an asset, there is no verifiable record of *which* models, prompts, and decisions produced it — a growing problem for newsrooms, agencies, and marketplaces that must prove "we made this, like this, at this time."

## 2. Solution

A generation studio with three load-bearing properties:

1. **Born verifiable.** Every asset gets a signed JSON manifest (prompt, model, provider, params, parent asset, timestamps, creator key) at the moment of creation.
2. **Sealed, not stored.** Manifests and pipeline receipts are written to a Backblaze B2 bucket with **Object Lock in compliance mode** — write-once-read-many. Not the user, not us, not a hacker with our keys, not Backblaze support can alter or delete them until retention expires. Hourly Merkle roots anchor all new manifests into a single locked object for independent proof-of-existence.
3. **Recoverable from abuse.** Alongside SHA-256, every asset gets a perceptual hash (pHash). The public verify page accepts a cropped, re-compressed, screenshotted copy and still resurrects its full birth certificate and lineage via Hamming-distance nearest-neighbor lookup.

Plus the ownership hook borrowed from the 0G winners: **the Vault is exportable.** One click produces a signed archive of the user's entire creative history — assets, manifests, lineage graph — that is verifiable offline, forever.

## 3. Why this wins (judging criteria mapping)

| Criterion | How Litmus scores |
|---|---|
| **Real-world utility** | Clear audiences: creators proving authorship, newsrooms/agencies needing audit trails, marketplaces needing provenance. The verify page works for *anyone*, not just users. |
| **Production readiness** | Resumable pipeline state persisted in B2; retries with judge scoring; WORM compliance storage; export; error states designed, not improvised. |
| **B2 Storage & Data Orchestration** | B2 is not a dumb file dump — Object Lock **is the product mechanism**, plus asset storage, thumbnails, pipeline state, Merkle anchors, and exportable archives. |
| **Use of Genblaze** | Genblaze orchestrates a modular multi-provider pipeline (image + audio + judge + retry). Every Genblaze step emits a provenance receipt — the SDK's orchestration *generates* the product's core data. |

**The demo moment that wins:** generate live → screenshot + crop the output in a paint tool → drag the mangled copy into the verify page → full birth certificate and pipeline lineage appear → attempt to delete the manifest from the B2 console live → **B2 refuses on camera.** The tamper-proof claim is proven, not asserted.

## 4. Users & personas

- **P1 — The working creator (primary).** Freelance designer/musician generating client assets. Needs: prove "I made this on this date with these tools" when disputes arise; keep a portable archive when platforms die.
- **P2 — The verifier (secondary, no account).** Editor, buyer, or moderator handed an image of unknown origin. Needs: drag it onto a page and get an answer in seconds.
- **P3 — The pipeline operator (aspirational).** Small studio running batch generation. Needs: audit trail of every model decision. Served by the same receipts; not a UI focus for v1.

## 5. Scope

### In scope (v1.0 — ship by deadline)
- Email-less demo auth (magic-link or single demo workspace with per-session keys) — 60-second onboarding rule.
- Text-to-image generation via Genblaze (GMI Cloud primary provider).
- Text-to-speech/audio narration via Genblaze (ElevenLabs or Stability Audio).
- The judge-retry loop: a vision/language model scores output vs. prompt; auto-retry up to 2× with revised params; every attempt logged.
- Signed manifests + receipts to Object-Locked B2 bucket (compliance mode, short retention — see §12 risk R1).
- SHA-256 + pHash fingerprinting; SQLite index for Hamming-distance lookup.
- Hourly (and on-demand) Merkle root anchoring.
- Public verify page (drag & drop, no login).
- Lineage view: parent → child asset graph per asset.
- Vault export: signed .zip of assets + manifests + verification script.
- Deployed public URL + public GitHub repo + 3-min demo video + Devpost + X post.

### Out of scope (v1.0) — say no, loudly
- Video generation (slow, flaky on demo day — roadmap slide only).
- Style capsules (the "load someone's creative memory" feature — v0.2 roadmap; **mention in pitch**, do not build).
- Real payments, teams/orgs, roles & permissions.
- C2PA embedding into files (roadmap; manifests are C2PA-shaped JSON).
- Steganographic watermarking (stretch; only if hours 18–20 are free).
- Mobile-optimized studio (verify page must be responsive; studio desktop-first).

---

## 6. Product specification

### 6.1 Information architecture

```
/                → Landing + verify drop zone (public)
/studio          → Generation studio (session)
/vault           → Asset grid + filters (session)
/asset/:id       → Asset detail: preview, manifest, receipts, lineage
/verify          → Full verify page (public, also embedded on /)
/export          → Vault export flow (session)
```

### 6.2 Feature: Studio

**User story:** As a creator, I type a prompt, optionally toggle "add narration," press Generate, and watch the pipeline work — every step visible, every step receipted.

**Flow:**
1. Prompt input (single textarea). Optional: narration toggle + narration text (defaults to the prompt).
2. On submit → POST /api/generate → pipeline starts → UI streams step events (SSE or 1s polling of run state).
3. Pipeline steps render as a vertical timeline, each step showing: name, provider/model, status (queued / running / passed / retried / failed), duration, and a "receipt sealed" checkmark with the receipt hash (first 8 chars, monospace).
4. On completion, the asset card appears with: preview, "Sealed" badge, verify link, and lineage entry.

**Acceptance criteria:**
- A failed provider call shows a retry event in the timeline, not a dead spinner.
- Killing the server mid-run and restarting resumes the run from B2 state (demo-able).
- Every completed run has ≥3 receipts (generate, judge, seal) visible on the asset page.

### 6.3 Feature: Judge-retry loop

- After generation, a judge model receives the prompt + output (image via vision model; audio via transcript/params heuristic for v1) and returns `{score: 0–100, reasons: []}`.
- `score < 70` → retry with revised params (seed change + judge reasons appended to prompt), max 2 retries.
- Every attempt — including rejected ones — is stored and receipted. Rejected attempts are visible in the asset's lineage as "discarded candidates." This is the audit-trail differentiator: the vault remembers what the pipeline *didn't* choose, and why.

### 6.4 Feature: Vault

- Grid of asset cards (newest first). Filters: type (image/audio/composite), date, "has lineage."
- Card: thumbnail (B2-served), title (first 6 words of prompt), created date, sealed badge, pHash chip.
- Empty state (see copy, §8.4).

### 6.5 Feature: Asset detail

- Large preview; audio gets a waveform player.
- **Birth certificate panel:** the manifest rendered as a clean definition list (not raw JSON by default; "View raw JSON" toggle). Fields: asset ID, created, creator key fingerprint, model + provider, prompt, params, SHA-256, pHash, parent asset (link), retention-locked-until date, Merkle root (link to anchor object).
- **Receipt chain panel:** ordered list of pipeline receipts; each row: step, timestamp, input hash → output hash, signature status (✓ verified in-browser via WebCrypto against the public key).
- **Lineage panel:** simple DAG rendered as an indented tree (v1) — parents above, discarded candidates collapsed below.

### 6.6 Feature: Verify (public)

- Full-bleed drop zone. Accepts image files (v1: png/jpg/webp; audio verify = exact-hash only for v1).
- Client computes SHA-256; server computes pHash; lookup order: exact SHA-256 match → pHash Hamming distance ≤ threshold (start at 10/64 bits; tune on test set).
- **Result states:**
  - **Exact match** → green result card: "Verified — bit-for-bit original." Full birth certificate.
  - **Perceptual match** → amber-green card: "Verified — modified copy of a sealed original (similarity 94%)." Side-by-side: uploaded vs. original thumbnail. Full birth certificate + note of confidence.
  - **No match** → neutral card: "No provenance found in this vault." Never claim the media is fake — absence of a record is not proof of anything (see copy, §8.6).
- Every result links to the Merkle anchor: "Independently verify: this record was sealed in batch #41, root `a3f9…` locked at 14:00 UTC."

### 6.7 Feature: Export

- One button → server assembles: `assets/`, `manifests/`, `receipts/`, `lineage.json`, `merkle-proofs/`, `verify.py` (offline verification script), `README.txt` → signs archive manifest → zip → download.
- Copy on the export screen makes the ownership promise explicit (§8.7).

### 6.8 Non-functional requirements

- Studio time-to-first-generation for a new visitor: **< 60 seconds** (the Ghast rule).
- Verify lookup: < 3s for a vault of 10k assets (SQLite BK-tree or linear scan is fine at hackathon scale; note scaling path in README).
- All B2 access via S3-compatible API; no vendor SDK lock beyond boto3-style config.
- Graceful degradation: if a provider is down, the pipeline retries once, then completes with a partial result + honest error receipt (yes, failures get receipts too).

---

## 7. UI specification — the anti-slop mandate

The fastest way to look like every vibe-coded hackathon app is: purple-to-blue gradient hero, glassmorphism cards, emoji in every heading, 14 shadcn components in default theme, confetti. **None of that ships.** Litmus's visual thesis is *archival*: it should feel like a cross between a bank vault ledger and a well-set photo book. Trust is the product; the UI must look like it was designed by someone who has met a ledger.

### 7.1 Design tokens

```css
/* Palette — "Ledger" */
--paper:      #F7F5F0;  /* app background — warm off-white, not #fff */
--ink:        #1A1917;  /* primary text — near-black, warm */
--ink-2:      #6B6862;  /* secondary text */
--line:       #E3E0D8;  /* hairline borders */
--seal:       #0F6E56;  /* the ONLY brand accent — deep verdigris green.
                           Used exclusively for sealed/verified states + primary CTA. */
--seal-tint:  #E1F5EE;
--amber:      #BA7517;  /* perceptual-match / caution */
--amber-tint: #FAEEDA;
--danger:     #A32D2D;  /* errors only. Never decorative. */
--mono-chip:  #EFECE4;  /* background for hashes/keys */

/* Type */
--font-display: "Newsreader", Georgia, serif;      /* headlines only */
--font-body:    "Inter", system-ui, sans-serif;     /* everything else */
--font-mono:    "JetBrains Mono", ui-monospace;     /* hashes, keys, receipts */

/* Scale: 13 / 15 / 17 / 22 / 30 / 44. Line-height 1.55 body, 1.15 display. */
/* Radius: 6px inputs & buttons, 10px cards. Nothing rounder. */
/* Shadows: none. Depth comes from hairlines and background steps. */
/* Spacing: 4px base grid; sections breathe at 64–96px. */
```

### 7.2 Rules (enforced, not aspirational)

1. One accent color. If a second decorative color appears, it's a bug.
2. Zero gradients, zero glass blur, zero drop shadows, zero confetti, zero emoji in UI chrome.
3. Every hash, key, and ID renders in mono inside a `--mono-chip` pill with a copy-on-click affordance. Truncate middle: `a3f9…c21b`.
4. Motion: 150ms ease-out opacity/transform only. The single earned animation: the seal stamp — when a receipt locks, its checkmark scales 0.8→1.0 once. No looping animations anywhere.
5. Buttons: primary = `--seal` fill, white text, sentence case ("Generate", "Verify a file", "Export vault"). Secondary = hairline outline. Never more than one primary button per view.
6. Empty states teach; they never just say "No items yet."
7. Timeline/receipt rows are table-like: fixed columns, tabular numerals, hairline separators — a ledger, not a chat feed.
8. The verify result card is the hero moment: full-width, generous padding, verdict in display serif, evidence in body sans. It should screenshot beautifully — judges will screenshot it.

### 7.3 Key screens (wireframe notes)

- **Landing:** display-serif headline over `--paper`, verify drop zone immediately visible (verb-first: judges test before reading), three-column "how it works" with line icons (Tabler, outline), footer with GitHub + "How sealing works" doc link. No hero image. No screenshot carousel.
- **Studio:** two columns. Left 40%: prompt card + options + Generate. Right 60%: run timeline (ledger rows) → completed asset card pinned at top. History of past runs below.
- **Asset detail:** preview left 55%, panels right 45% stacked: Birth certificate / Receipts / Lineage. Print-friendly (`@media print`) — a birth certificate you can literally print is a talking point.
- **Verify:** drop zone → skeleton (3 shimmering ledger rows, 150ms fade) → verdict card.

---

## 8. Full product copy

Voice: calm, precise, quietly confident. Bank-ledger energy, not startup energy. No exclamation marks anywhere in the product. Contractions allowed. Never say "magic," "supercharge," "unleash," "blazing," or "revolutionary."

### 8.1 Landing
- **H1:** `Your creative memory, sealed.`
- **Sub:** `Litmus is a generation studio where every AI asset is born with a signed birth certificate — stored in write-once vault storage that nobody can rewrite. Not us. Not anyone.`
- **Primary CTA:** `Open the studio`
- **Secondary:** `Verify a file` (anchors to drop zone)
- **Drop zone:** `Drop any image here to run the litmus test on its provenance.` / small text: `Works even on cropped or re-compressed copies. No account needed.`
- **Three-up:**
  1. `Born verifiable` — `Every generation is signed at birth: prompt, model, time, and author, sealed the moment it exists.`
  2. `Sealed in WORM storage` — `Records live in compliance-locked storage. Write once, read forever, alter never.`
  3. `Survives the screenshot` — `Perceptual fingerprints recover an asset's history from cropped, compressed, or messaged copies.`
- **Footer line:** `Built on Backblaze B2 Object Lock and the Genblaze pipeline SDK.`

### 8.2 Studio
- **Prompt label:** `What are we making?`
- **Placeholder:** `A lighthouse keeper's desk at dawn, tilt-shift, warm film grain…`
- **Narration toggle:** `Add narration` / helper: `We'll generate a voice track and seal it to the same lineage.`
- **Button:** `Generate` → running: `Sealing as we go…`
- **Timeline step labels:** `Generate image — GMI Cloud / FLUX`, `Judge — scoring against your prompt`, `Retry 1 of 2 — seed changed, judge notes applied`, `Seal — receipt locked to vault`
- **Judge fail note:** `Judge scored 58/100: "subject off-frame; palette ignored." Retrying with adjusted parameters. The rejected attempt stays in your lineage.`
- **Run complete:** `Sealed. This asset now has a permanent, verifiable history.`

### 8.3 Asset detail
- **Sealed badge:** `Sealed · cannot be altered until Mar 2027`
- **Birth certificate header:** `Birth certificate`
- **Receipts header:** `Receipt chain` / sub: `Every pipeline decision, signed and locked — including the attempts we threw away.`
- **Lineage header:** `Lineage` / discarded group label: `Discarded candidates (2) — kept for the record`
- **Copy hash toast:** `Copied.`

### 8.4 Vault empty state
`Nothing in the vault yet. Generate your first asset and it will appear here with its birth certificate — sealed, signed, and yours to export at any time.`

### 8.5 Verify results
- **Exact:** H: `Verified — original file.` Body: `This file matches a sealed record bit for bit. Its full history is below.`
- **Perceptual:** H: `Verified — modified copy.` Body: `This file is a close derivative of a sealed original (similarity 94%). It has been re-encoded, cropped, or resized since sealing. The original and its history are below.`
- **No match:** H: `No record found.` Body: `This vault holds no sealed record matching this file. That doesn't prove the file is AI-generated or authentic — only that it wasn't sealed here.`
- **Anchor line (all matches):** `Independently verifiable: sealed in batch #41, Merkle root a3f9…c21b, locked 2026-08-03 14:00 UTC.`

### 8.6 Errors
- Provider down: `GMI Cloud isn't responding. We retried once and logged the failure to your receipt chain. Try again, or switch providers in options.`
- Upload too large (verify): `Files up to 25 MB for now. For anything larger, verification by hash is in the docs.`
- Generic: `Something failed on our side. Nothing was lost — your vault only ever gains records, it never loses them.`

### 8.7 Export
- **H:** `Take everything with you.`
- **Body:** `Your export contains every asset, manifest, receipt, and Merkle proof in your vault, plus a small offline script that verifies all of it without us. If Litmus disappeared tomorrow, this archive would still prove what you made, and when.`
- **Button:** `Export vault (.zip)`

### 8.8 Pipeline prompts (the actual prompts)

**Judge system prompt (vision model):**
```
You are a strict art director scoring one generated image against the brief.
Return ONLY JSON: {"score": <0-100>, "reasons": ["<short reason>", ...]}
Score dimensions: subject fidelity to brief (40), composition (25),
technical artifacts (20), style adherence (15).
Under 70 means "reject and retry." Be specific and terse in reasons —
they are fed back into the retry prompt verbatim.
```

**Retry prompt template:**
```
{original_prompt}

Revision notes from art direction (address all):
{judge_reasons_bulleted}
```

**Narration prompt template (TTS input builder):**
```
Write a single spoken sentence (max 22 words) describing this scene
for a gallery placard, neutral documentary tone: "{original_prompt}"
```

---

## 9. System architecture & implementation

### 9.1 Stack
- **Backend:** Python 3.11, FastAPI, uvicorn. Genblaze SDK for orchestration. boto3 against B2's S3-compatible endpoint. `imagehash` (pHash), `cryptography` (Ed25519), SQLite (+ simple BK-tree or linear Hamming scan).
- **Frontend:** Next.js (or plain React + Vite) — server-rendered landing/verify for speed; studio as SPA. Tailwind with the §7.1 tokens mapped into the config; **do not** use default Tailwind blue/violet anywhere.
- **Deploy:** single VM or Railway/Fly/Render; frontend on same origin to dodge CORS during the crunch.

### 9.2 Buckets & key layout

```
lm-assets            (no lock)      — generated media + thumbnails
  assets/{asset_id}/original.png
  assets/{asset_id}/thumb.webp
  assets/{asset_id}/narration.mp3

lm-vault             (Object Lock: COMPLIANCE, retention 7 days for demo)
  manifests/{asset_id}.json
  receipts/{run_id}/{seq:03d}-{step}.json
  anchors/{yyyy-mm-ddThh}.root.json

lm-state             (no lock)      — resumable pipeline state
  runs/{run_id}/state.json
  exports/{export_id}.zip
```

- Retention is **7 days** for the hackathon (compliance mode is irreversible — see R1). README documents flipping to 365+ for production.
- Create the lock at bucket creation: `CreateBucket` with `ObjectLockEnabledForBucket=True`, then `PutObjectLockConfiguration` (COMPLIANCE, days=7). Per-object headers on every vault write: `x-amz-object-lock-mode: COMPLIANCE`, `x-amz-object-lock-retain-until-date`.

### 9.3 Data models (JSON schemas, abbreviated)

**Manifest (`manifests/{asset_id}.json`):**
```json
{
  "schema": "litmus/manifest@1",
  "asset_id": "ast_7f3k9",
  "created_utc": "2026-08-03T10:22:41Z",
  "creator_pubkey": "ed25519:BASE64…",
  "kind": "image",
  "prompt": "…",
  "provider": "gmi-cloud",
  "model": "flux-1.1",
  "params": {"seed": 8812, "size": "1024x1024"},
  "sha256": "…",
  "phash64": "d1b2…",
  "parent_asset": "ast_2c8m1 | null",
  "run_id": "run_x91",
  "retain_until": "2026-08-10T00:00:00Z",
  "signature": "BASE64(Ed25519 over canonical JSON minus this field)"
}
```

**Receipt (`receipts/{run_id}/{seq}-{step}.json`):**
```json
{
  "schema": "litmus/receipt@1",
  "run_id": "run_x91", "seq": 2, "step": "judge",
  "ts_utc": "…", "provider": "gmi-cloud", "model": "qwen-vl",
  "input_sha256": "…", "output_sha256": "…",
  "detail": {"score": 58, "reasons": ["subject off-frame"]},
  "prev_receipt_sha256": "…",
  "signature": "…"
}
```
`prev_receipt_sha256` chains receipts per run — a mini hash chain inside WORM storage.

**Anchor:** `{"schema":"litmus/anchor@1","batch":"2026-08-03T14","merkle_root":"…","leaf_count":37,"leaves_prefix":"manifests/"}`. Cron hourly + `POST /api/anchor` for the demo.

### 9.4 Genblaze pipeline (modular steps — the anima lesson)

```python
# pipeline.py — every step: (a) does work, (b) writes state, (c) emits sealed receipt
STEPS = [gen_image, judge, maybe_retry, gen_narration, fingerprint, seal_manifest]

async def run_pipeline(run_id, brief):
    state = load_state(run_id) or new_state(brief)      # resume-from-B2
    for step in STEPS[state.next_step:]:
        out = await step(state)                          # Genblaze provider calls inside
        state = advance(state, out); save_state(run_id, state)   # lm-state
        seal_receipt(run_id, state.seq, step.__name__, out)      # lm-vault, locked
    return state.asset
```
Genblaze specifics: use its provider registry for GMI Cloud (image) + ElevenLabs/Stability (audio); use its retry/fallback hooks so a provider stall triggers the fallback provider — and receipt the fallback. That single behavior is your "production readiness" paragraph.

### 9.5 API surface

```
POST /api/generate          {prompt, narration?}            → {run_id}
GET  /api/runs/{run_id}     → state + step events (poll)     [or SSE /api/runs/{id}/events]
GET  /api/assets            → vault list
GET  /api/assets/{id}       → manifest + receipts + lineage
POST /api/verify            multipart file                   → verdict payload
POST /api/export            → {export_id}; GET /api/exports/{id} → signed URL
POST /api/anchor            → force Merkle anchor (demo)
```

### 9.6 Verification logic

1. SHA-256 exact lookup in SQLite → exact verdict.
2. Else compute pHash (64-bit dHash+pHash combo), scan index for Hamming ≤ 10 → best match + similarity `1 − d/64`.
3. Fetch manifest from `lm-vault`, verify Ed25519 signature **in the browser** (ship the pubkey; WebCrypto) — "don't trust our server, check the math yourself" is a pitch line.
4. Recompute Merkle inclusion from the anchor object; show proof link.

### 9.7 Setup (from zero)

```bash
# 1. Backblaze
#    - Create account → create key pair (master for setup, app key for runtime)
#    - Create lm-assets (public-read via CF/B2 URL for thumbs), lm-state,
#      and lm-vault WITH Object Lock enabled at creation (cannot be added later)
# 2. Providers: GMI Cloud key (hackathon credits), ElevenLabs key
# 3. Repo
git clone <repo> && cd litmus
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn boto3 genblaze imagehash cryptography pillow python-multipart
cp .env.example .env    # B2_ENDPOINT, B2_KEY_ID, B2_APP_KEY, GMI_KEY, ELEVEN_KEY,
                        # VAULT_RETENTION_DAYS=7, SIGNING_KEY_PATH
python scripts/gen_keys.py          # Ed25519 keypair; pubkey baked into frontend
python scripts/create_buckets.py    # idempotent; sets lock config
uvicorn app:app --reload
cd web && npm i && npm run dev
```

---

## 10. Demo video script (3:00)

- **0:00–0:20 — Problem.** Screen-record: right-click-save an AI image, open properties: nothing. "Every AI asset is an orphan the moment it leaves the generator."
- **0:20–1:10 — Studio.** Type prompt, toggle narration, Generate. Let the timeline breathe: judge rejects attempt 1 on camera ("58/100 — subject off-frame"), retry passes, seal stamps. "Every decision — including the one we threw away — is now a locked receipt."
- **1:10–2:00 — The abuse test.** Screenshot the output, crop it badly in Paint, drop it on /verify. Verdict card: *Verified — modified copy, similarity 94%*, full birth certificate. "Metadata dies at the first screenshot. Litmus doesn't."
- **2:00–2:35 — The refusal.** Open B2 console, attempt to delete the manifest. **B2 refuses on screen.** "Compliance-mode Object Lock. Not us, not you, not Backblaze can rewrite history."
- **2:35–3:00 — Ownership + close.** Click Export, show the zip's verify.py running offline: `37/37 records verified`. "Your creative memory, as an asset. Built on B2 and Genblaze." URL + repo on end card.

## 11. Submission copy

- **Devpost one-liner:** `A generation studio where every AI asset is born with a signed birth certificate, sealed in write-once B2 storage, and verifiable even from a cropped screenshot.`
- **Providers & models:** GMI Cloud (FLUX image gen; Qwen-VL judge), ElevenLabs (TTS). Orchestrated by Genblaze.
- **B2 & Genblaze usage (verbatim for the form):** `B2 stores assets, thumbnails, and resumable pipeline state; Object Lock in compliance mode seals manifests, per-step receipts, and hourly Merkle anchors — the tamper-proof property IS a B2 storage feature. Genblaze orchestrates the modular pipeline (generate → judge → retry → narrate → seal) across GMI Cloud and ElevenLabs with provider fallback; every Genblaze step emits a signed receipt, so the SDK's orchestration generates the product's core data.`
- **X post:** `Every AI image is an orphan the moment you screenshot it. We built Litmus: assets born with signed birth certificates, sealed in write-once storage, recoverable from a cropped screenshot. No blockchain — a storage bucket. [demo clip] @Backblaze #BackblazeHackathon`

## 12. Negatives — risks, weaknesses, honest limitations

*(Name these in the README and Q&A before judges do; the playbook rewards it.)*

- **R1 — Compliance lock is irreversible.** A bug that writes garbage to lm-vault means garbage locked for the retention period. Mitigation: 7-day demo retention; schema-validate before every locked write; staging bucket in governance mode for development.
- **R2 — pHash false positives/negatives.** Heavy crops (>60%), mirrors, and rotations defeat pHash; distinct-but-similar images can collide at loose thresholds. Mitigation: conservative threshold (≤10/64), always pair with exact-hash + signature for the "bit-for-bit" claim, show similarity % instead of a binary yes, and state the limit in the verify UI footnote. Roadmap: multi-crop hashing + embedding-based ANN.
- **R3 — Trust root is our signing key.** v1 proves *this service* sealed the record at time T; it does not prove the human behind the account. Honest framing: "tamper-evident notarization," not identity attestation. Roadmap: per-user keys (already schema'd via `creator_pubkey`), optional public transparency log of anchors (tweeted roots).
- **R4 — Absence isn't evidence.** "No record found" must never be presented as "this is fake." The copy in §8.5 enforces this; do not soften it under demo pressure.
- **R5 — Provider flakiness on demo day.** GMI/ElevenLabs latency or outage mid-video. Mitigation: Genblaze fallback provider configured; pre-recorded demo video is the submission artifact; live demo only if asked.
- **R6 — Cost/abuse of public verify.** Unauthenticated upload endpoint. Mitigation: 25 MB cap, rate-limit by IP, strip and never store uploaded verify files.
- **R7 — Privacy of prompts.** Manifests contain prompts and are designed to be shown to verifiers. Mitigation: a "private manifest" mode is out of scope; disclose clearly in studio helper text: `Anyone who verifies this asset can read its prompt.`
- **R8 — Merkle anchor centralization.** We compute the root; a malicious operator could fork history before anchoring. Mitigation (honest): locked receipts make retroactive edits impossible, but pre-seal manipulation is a trust gap; roadmap is publishing roots externally (X post per batch = free transparency log).
- **R9 — One-person build risk.** Scope creep kills this. The §5 out-of-scope list is contractual; style capsules are a slide, not code.

## 13. Build plan (T-minus ~20 hours)

| Hours | Deliverable |
|---|---|
| 0–2 | Buckets + lock config script, keys, FastAPI skeleton, .env, deploy pipeline working (deploy FIRST, iterate live) |
| 2–6 | Genblaze pipeline: image gen + judge + retry + receipts + manifests sealed to lm-vault; resumable state |
| 6–8 | Fingerprinting + SQLite index + /api/verify with all three verdicts |
| 8–12 | Frontend: studio + timeline + asset detail (tokens from §7; copy from §8 verbatim) |
| 12–14 | Verify page + landing; in-browser signature check |
| 14–15 | Narration step + lineage view |
| 15–16 | Export + verify.py |
| 16–17 | Merkle anchoring + anchor links in UI |
| 17–19 | Record demo video (script §10), screenshots, README with §12 negatives |
| 19–20 | Devpost + X post, repo public, buffer |

**Cut order if behind:** narration → lineage tree (keep parent link as text) → export UI (keep API + curl demo) → Merkle (keep per-object lock story). **Never cut:** judge-retry receipts, Object Lock, verify page, the delete-refusal demo.

## 14. Success metrics (hackathon-scale)

- Submission complete with all 6 required artifacts before deadline. 
- Demo video shows the delete-refusal moment.
- ≥1 external person uses /verify before submission (screenshot it → "traction" line in Devpost, the Ghast lesson).
- Zero gradients shipped.

## 15. Roadmap (one slide, spoken not built)

v0.2 Style capsules — export a slice of your creative memory others can generate with, provenance-credited. v0.3 C2PA embedding + per-user keys. v0.4 Video pipeline + embedding-based verify at scale. v1.0 Team vaults with B2 Event-Notification-driven auto-sealing of any watched bucket.
