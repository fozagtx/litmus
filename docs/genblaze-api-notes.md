# Genblaze SDK — verified API notes (from installed source, v0.4.5)

These notes were extracted by reading the installed packages in
`.venv/lib/python3.11/site-packages/` (genblaze-core 0.3.8, genblaze-s3 0.3.6,
genblaze-gmicloud 0.3.5, genblaze-elevenlabs 0.3.3). Everything below is the
real API — do not invent methods that are not listed here. When in doubt, read
the source at the paths given.

## Imports

```python
from genblaze import (
    Pipeline, PipelineResult, Step, Run, Manifest,
    ObjectStorageSink, ObjectLockConfig, StorageConfig, KeyStrategy,
    Evaluator, EvaluationResult, CallableEvaluator, ThresholdEvaluator,
    AgentLoop, AgentContext, AgentResult, AgentIteration,
    Modality, StepStatus, StepType, RunStatus, PromptVisibility,
    ProviderError, PipelineError, GenblazeError, StorageError,
)
from genblaze_s3 import S3StorageBackend           # NOT re-exported by umbrella
from genblaze_gmicloud.image import GMICloudImageProvider
from genblaze_gmicloud.chat import chat            # plain function, OpenAI-wire chat
from genblaze_elevenlabs import ElevenLabsTTSProvider
```

## Providers

### GMICloudImageProvider (`genblaze_gmicloud/image.py`)
- `name = "gmicloud-image"`. Auth: `GMI_API_KEY` env var or `api_key=` kwarg.
- Ctor: `GMICloudImageProvider(api_key=None, poll_interval=5, http_timeout=120, base_url=None, models=None)`
- Submits to GMICloud request queue, polls, returns `Asset(url=..., media_type=...)`
  appended to `step.assets` — asset URL is a REMOTE GMI url until a sink transfers it.
- Model slugs (registry is permissive — unknown slugs pass through): Seedream
  (`seedream-*`), Gemini Flash Image, FLUX-Kontext (`flux-kontext-*`), Reve,
  Bria. Families with dedicated payload shapes: `bria-genfill|bria-eraser`,
  `seededit-*|reve-edit*|reve-remix*`, `gpt-image-2-edit`.
- Common params (pass via `Pipeline.step(..., params={...})` or kwargs):
  `size="1024x1024"`, `seed=<int>` etc. — permissive passthrough surface.

### chat() (`genblaze_gmicloud/chat.py`) — use for the JUDGE
```python
chat(model, messages=None, *, prompt=None, system=None, tools=None,
     temperature=None, max_tokens=None, response_format=None,
     api_key=None, base_url=None, timeout=60.0, **kwargs) -> ChatResponse
```
- OpenAI wire-compatible (`POST /chat/completions`); model ids like
  `"deepseek-ai/DeepSeek-V3"`, `"meta-llama/Llama-3.3-70B-Instruct"`,
  `"Qwen/Qwen2.5-VL-72B-Instruct"` (vision).
- `messages` accepts OpenAI-style dicts, including vision content parts:
  `{"role":"user","content":[{"type":"text","text":...},{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]}`.
- `response_format` accepts a Pydantic BaseModel subclass → structured output.
- `ChatResponse` (genblaze_core/models/chat.py): has `.content` (str) among fields — check source if you need more.
- Raises `ProviderError` with classified `error_code` on failure.

### ElevenLabsTTSProvider (`genblaze_elevenlabs/provider.py`)
- `name = "elevenlabs-tts"`, extends `SyncProvider`. Auth: `ELEVENLABS_API_KEY`
  env var or `api_key=`.
- Ctor: `ElevenLabsTTSProvider(api_key=None, output_dir=None, *, models=None, ...)`
  — writes output audio files locally to `output_dir` (default system temp);
  the step asset URL will be a local file path/URI until a sink transfers it.
- Models: any `eleven_*` slug — `eleven_multilingual_v2`, `eleven_flash_v2_5`,
  `eleven_turbo_v2_5`, `eleven_v3`.
- Step params: `voice_id` (default `"JBFqnCBsd6RMkjVDRZzb"`), `stability`,
  `similarity_boost`, `style`, `output_format`.
- Use `modality=Modality.AUDIO` on the step.

## Pipeline (`genblaze_core/pipeline/pipeline.py`)

```python
p = Pipeline("litmus-generate", tenant_id=None, chain=False, preflight=True)
p.step(provider,                     # BaseProvider INSTANCE (TypeError otherwise)
       model="seedream-4-0",         # required kwarg
       prompt="...",                 # str or PromptTemplate
       modality=Modality.IMAGE,
       step_type=StepType.GENERATE,
       fallback_models=None,         # list[str] — SDK-native fallback story
       input_from=None,              # int | list[int] — wire prior step outputs in
       external_inputs=None,         # list[Asset] — caller-held inputs (excl. with input_from)
       metadata={...},               # merged into Step.metadata (no reserved keys)
       prompt_visibility=PromptVisibility.PUBLIC,
       params={"size": "1024x1024", "seed": 1234},   # provider params
       )                              # returns self — chainable
result = p.run(raise_on_failure=False)   # PipelineResult; pass explicit bool to
                                         # silence the 0.4.0 deprecation warning
```
- `p.run()` returns `PipelineResult(run, manifest)`; supports `run, manifest = result` unpacking.
- `result.failed_steps()`, `result.succeeded_steps()`, `result.error_summary()`.
- `result.save(path, embed=True)` → embeds the manifest INTO the media file
  (PNG/JPEG/MP3/WAV/...) or writes a sidecar. Returns EmbedResult.
- `p.stream(heartbeats=True, **run_kwargs)` → generator of `StreamEvent`s
  (StepQueuedEvent, StepStartedEvent, StepCompleteEvent, PipelineCompletedEvent,
  PipelineFailedEvent, progress). Each has `.to_dict()` (JSON-safe) and `.type`
  (StreamEventType enum). `p.astream()` for async.
- `p.arun()` async variant. `p.metadata(**kw)` merges into Run.metadata.
- `Pipeline(..., preflight=False)` skips model validation calls (use for speed;
  keep default True in production paths).
- `p.resume_step(...)` exists for resuming; check source before using.
- Async: `arun`, `astream`, `abatch_run`.
- Steps run CONCURRENTLY unless `chain=True` or `input_from=` creates deps.

## Judge-retry: AgentLoop (`genblaze_core/agents/loop.py`)

```python
loop = AgentLoop(
    pipeline_factory,      # Callable[[AgentContext], Pipeline] — fresh pipeline per attempt;
                           # ctx carries prior iterations + last evaluation feedback
    evaluator,             # Evaluator instance
    max_iterations=3,      # 1 initial + up to 2 retries
    stop_on_pipeline_failure=True,
)
agent_result = loop.run(raise_on_failure=False)   # run_kwargs forwarded to Pipeline.run()
# also: loop.arun(), loop.stream(), loop.astream()
```
- `AgentContext`: has `.iteration` (int), `.previous` (list[AgentIteration]),
  and last feedback — read `genblaze_core/agents/loop.py` `_make_context` for exact fields.
- `AgentIteration(index, result: PipelineResult, evaluation: EvaluationResult)`.
- `AgentResult`: `.iterations` (all attempts, INCLUDING rejected ones — this is
  the discarded-candidates audit trail), plus final/passed accessors — read
  the class for exact field names before use.
- `EvaluationResult(passed: bool, score: float|None, feedback: str|None, metadata: dict)`.
- Write the judge as a custom `Evaluator` subclass whose `evaluate(result)`
  downloads the image bytes, calls `chat()` with the vision model + strict JSON
  response_format, and returns EvaluationResult(score 0–100 scaled, feedback
  = judge reasons joined). Score < 70 → `passed=False`.

## Storage: S3StorageBackend (`genblaze_s3/backend.py`)

```python
backend = S3StorageBackend.for_backblaze(
    bucket="lm-vault",            # or env B2_BUCKET
    region="us-west-004",         # or env B2_REGION; endpoint https://s3.{region}.backblazeb2.com
    key_id=..., app_key=...,      # or env B2_KEY_ID / B2_APP_KEY
    public_url_base=None,         # e.g. "https://f004.backblazeb2.com/file/lm-assets"
    preflight=True,               # verifies bucket region at construction; raises StorageError
)
```
Methods (all sync):
- `put(key, data: bytes|BinaryIO, *, content_type=None, metadata=None, extra_args=None, object_lock: ObjectLockConfig|None=None) -> str` (returns key). `object_lock=` applies per-object retention — THIS is how receipts/manifests/anchors get compliance-locked.
- `get(key) -> bytes`, `exists(key) -> bool`, `head(key) -> ObjectMetadata|None`,
  `list(prefix=...)` → ListPage (check signature), `get_range`, `stream`.
- `delete(key)`, `delete_many`, `delete_prefix` — will FAIL on locked objects (the demo moment).
- `presigned_get(key, ...)`, `presigned_put(...)`, `get_url(key)`, `get_durable_url(key)`.
- `copy(src, dst)`.
- One backend instance per bucket. Litmus needs three: lm-assets, lm-vault, lm-state.

## ObjectLockConfig (`genblaze_core/storage/base.py`)

```python
from datetime import datetime, timedelta, timezone
lock = ObjectLockConfig(
    retain_until=datetime.now(timezone.utc) + timedelta(days=7),  # MUST be tz-aware
    mode="COMPLIANCE",           # or "GOVERNANCE" (default)
)
lock.to_extra_args()  # {"ObjectLockMode": ..., "ObjectLockRetainUntilDate": ...}
```
Bucket MUST be created with Object Lock enabled (cannot be enabled later).

## ObjectStorageSink (`genblaze_core/storage/sink.py`)

```python
sink = ObjectStorageSink(
    backend,
    prefix="genblaze",
    key_strategy=KeyStrategy.CONTENT_ADDRESSABLE,   # or HIERARCHICAL (per-run grouping)
    manifest_lock=ObjectLockConfig(...),            # locks the SDK manifest on write_run
    eager_transfer=False,
)
sink.write_run(run, manifest)        # transfers step assets to B2 (rewrites asset.url
                                     # to durable URLs) + writes locked manifest
sink.manifest_key_for(run) -> str
sink.manifest_url_for(run) -> str
sink.read_manifest(...)              # check signature before use
sink.put_asset(...) / put_assets(...)
sink.close()
```
- After `write_run`, `run.steps[i].assets[j].url` points at durable B2 URLs and
  `.sha256` is populated. Use those for Litmus's own manifest/fingerprinting.

## Manifest (`genblaze_core/models/manifest.py`)
- `Manifest.from_run(run)` → computes `canonical_hash` (SHA-256 of canonical JSON;
  operational fields excluded).
- `manifest.to_canonical_json()`, `manifest.verify()`, `manifest.verify_hash()`,
  `manifest.verification_report()`.
- `parse_manifest(...)` module function for reading back.
- The SDK manifest complements (does not replace) Litmus's own signed
  `litmus/manifest@1` JSON — seal BOTH: the SDK manifest via sink.write_run's
  manifest_lock, and the Litmus manifest via `backend.put(..., object_lock=...)`.

## Errors
- `ProviderError(message, error_code: ProviderErrorCode, retry_after=...)`;
  `PipelineError`, `PipelineTimeoutError`, `BatchPipelineError`, `StorageError`
  (with `StorageErrorCode`), `GenblazeError` base.
- `Step.retryable` property — True when error_code is transient.

## Gotchas
1. `Pipeline.step()` requires a `BaseProvider` INSTANCE (not class, not function).
2. `params={"inputs": ...}` / `params={"metadata": ...}` raise — reserved names.
3. `raise_on_failure` unset emits a DeprecationWarning — always pass it explicitly.
4. `ObjectLockConfig.retain_until` must be timezone-aware or ValueError.
5. `for_backblaze(preflight=True)` raises at construction with bad creds —
   construct backends lazily at startup and surface a clear error, don't crash imports.
6. ElevenLabs provider writes audio to LOCAL disk first (`output_dir=`);
   pass a workdir you control so you can fingerprint the bytes.
7. GMI image asset URL is remote until transferred; download bytes yourself
   (httpx) for pHash/SHA-256 before/independent of sink transfer.
8. COMPLIANCE-mode sink logs a loud warning at construction — expected, leave it.

## Google provider (added after GMI-credits fallout)

- `from genblaze_google.gemini_image import GeminiImageProvider` — name
  "google-gemini-image", env `GEMINI_API_KEY`, models `^gemini-.*-image`
  (e.g. `gemini-2.5-flash-image`). Writes output images to LOCAL disk
  (`output_dir=`); asset.url is a local path — use providers.read_asset_bytes.
  Only the prompt is honored; seed/size params are not sent.
- `from genblaze_google.chat import chat` — Gemini chat; env `GEMINI_API_KEY`;
  NO response_format/timeout params. Extra kwargs merge into generation_config
  (`response_mime_type="application/json"` for JSON mode). Vision via typed
  ChatMessage with TextContent/ImageURLContent blocks (data: URI → inline_data).
- Requires `google-genai` package at runtime.
- server/providers.py is the dispatch seam: AI_PROVIDER=google|gmicloud.
