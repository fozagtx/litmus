"""Litmus FastAPI application — API under /api, SPA served from web/dist."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server import b2, config, export, index, media, merkle, pipeline, verify
from server import runstate as rs
from server.config import ConfigError, PROJECT_ROOT
from server.signing import fingerprint, public_key_b64, signing_key_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("litmus.main")

WEB_DIST = PROJECT_ROOT / "web" / "dist"

ANCHOR_INTERVAL_SEC = 3600


@asynccontextmanager
async def lifespan(app: FastAPI):
    index.init_db()
    # Rebuild the index from the vault when empty (fresh deploy / lost db).
    try:
        if index.count_assets() == 0 and not config.missing_for("b2_vault"):
            await anyio.to_thread.run_sync(index.reindex_from_vault)
    except Exception as exc:  # noqa: BLE001 — startup must not crash on B2 issues
        logger.error("startup reindex failed: %s", exc)
    # Resume interrupted runs from lm-state.
    try:
        if not config.missing_for("b2_state"):
            await anyio.to_thread.run_sync(pipeline.resume_incomplete)
    except Exception as exc:  # noqa: BLE001
        logger.error("startup resume failed: %s", exc)
    anchor_task = asyncio.create_task(_hourly_anchor())
    yield
    anchor_task.cancel()


async def _hourly_anchor() -> None:
    while True:
        try:
            await asyncio.sleep(ANCHOR_INTERVAL_SEC)
            if config.missing_for("b2_vault"):
                continue
            anchor = await anyio.to_thread.run_sync(merkle.anchor_new)
            if anchor is None:
                logger.info("hourly anchor: nothing new to anchor")
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 — keep the loop alive
            logger.error("hourly anchor failed: %s", exc)


app = FastAPI(title="Litmus", lifespan=lifespan)
app.include_router(media.router)


# --- health & keys ----------------------------------------------------------

def _check_ai_provider() -> tuple[bool, str]:
    key = config.gemini_api_key()
    if not key:
        return False, "missing env var: GEMINI_API_KEY"
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    headers = {"x-goog-api-key": key}
    display = "Google Gemini"
    try:
        resp = httpx.get(url, headers=headers, timeout=8.0)
        if resp.status_code == 200:
            return True, f"{display} reachable, key accepted"
        if resp.status_code in (400, 401, 403):
            return False, f"{display} rejected the API key (HTTP {resp.status_code})"
        return True, (
            f"key set; catalog endpoint returned HTTP {resp.status_code} — "
            "run scripts/check_providers.py for a live model check"
        )
    except Exception as exc:
        return False, f"{display} unreachable: {exc}"


def _check_elevenlabs() -> tuple[bool, str]:
    key = config.elevenlabs_api_key()
    if not key:
        return False, "missing env var: ELEVENLABS_API_KEY"
    try:
        resp = httpx.get(
            "https://api.elevenlabs.io/v1/models",
            headers={"xi-api-key": key},
            timeout=8.0,
        )
        if resp.status_code == 200:
            return True, "ElevenLabs reachable, key accepted"
        if resp.status_code in (401, 403):
            return False, f"ElevenLabs rejected the API key (HTTP {resp.status_code})"
        return False, f"ElevenLabs returned HTTP {resp.status_code}"
    except Exception as exc:
        return False, f"ElevenLabs unreachable: {exc}"


@app.get("/api/health")
async def health() -> dict[str, Any]:
    async def run(fn):
        try:
            return await anyio.to_thread.run_sync(fn)
        except Exception as exc:  # noqa: BLE001 — health never crashes
            return False, str(exc)

    results = await asyncio.gather(
        run(lambda: b2.health_check("assets")),
        run(lambda: b2.health_check("vault")),
        run(lambda: b2.health_check("state")),
        run(_check_ai_provider),
        run(_check_elevenlabs),
        run(signing_key_available),
    )
    names = ["b2_assets", "b2_vault", "b2_state", "ai", "elevenlabs", "signing_key"]
    checks = {n: {"ok": ok, "detail": detail} for n, (ok, detail) in zip(names, results)}
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


@app.get("/api/pubkey")
def pubkey() -> dict[str, str]:
    try:
        return {
            "pubkey_b64": public_key_b64(),
            "fingerprint": fingerprint(),
            "algorithm": "ed25519",
        }
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# --- generate & runs --------------------------------------------------------

class GenerateBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    narration: bool = False
    narration_text: str | None = Field(default=None, max_length=4000)


def _require_or_503(*subsystems: str) -> None:
    for sub in subsystems:
        try:
            config.require(sub)
        except ConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    ok, detail = signing_key_available()
    if not ok:
        raise HTTPException(status_code=503, detail=detail)


@app.post("/api/generate", status_code=202)
def generate(body: GenerateBody) -> dict[str, str]:
    subsystems = ["b2_assets", "b2_vault", "b2_state", "ai"]
    if body.narration:
        subsystems.append("elevenlabs")
    _require_or_503(*subsystems)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Prompt must not be empty.")
    state = rs.create_run(prompt, body.narration, body.narration_text)
    pipeline.start_run(state.run_id)
    return {"run_id": state.run_id}


@app.get("/api/runs")
def list_runs() -> dict[str, Any]:
    return {"runs": [s.model_dump(mode="json") for s in rs.list_states()]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    state = rs.get_state(run_id)
    if state is None:
        entry = None
        if not config.missing_for("b2_state"):
            entry = rs.load_from_state_store(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Unknown run {run_id!r}")
        state = entry.state
    return state.model_dump(mode="json")


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    if rs.get_state(run_id) is None:
        if not config.missing_for("b2_state"):
            await anyio.to_thread.run_sync(rs.load_from_state_store, run_id)
    if rs.get_state(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown run {run_id!r}")

    async def event_stream():
        seen_version = -1
        while True:
            if await request.is_disconnected():
                return
            entry = rs.get_entry(run_id)
            if entry is None:
                return
            with entry.cond:
                version = entry.version
                state = entry.state.model_dump(mode="json")
            if version > seen_version:
                seen_version = version
                yield f"data: {_json_dumps(state)}\n\n"
                if state["status"] in ("complete", "failed"):
                    return
            new_version = await anyio.to_thread.run_sync(
                rs.wait_for_change, run_id, seen_version, 15.0
            )
            if new_version is None:
                yield ": keep-alive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# --- assets -----------------------------------------------------------------

@app.get("/api/assets")
def list_assets(
    kind: str | None = None,
    has_lineage: str | None = None,
    include_discarded: str | None = None,
) -> dict[str, Any]:
    lineage_filter: bool | None = None
    if has_lineage is not None and has_lineage != "":
        lineage_filter = has_lineage in ("1", "true", "yes")
    rows = index.list_assets(
        kind=kind or None,
        include_discarded=include_discarded in ("1", "true", "yes"),
        has_lineage=lineage_filter,
    )
    return {"assets": [verify.asset_summary(r) for r in rows]}


@app.get("/api/assets/{asset_id}")
def get_asset(asset_id: str) -> dict[str, Any]:
    row = index.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset {asset_id!r}")
    try:
        manifest = b2.get_json("vault", row["manifest_key"])
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not load manifest from vault: {exc}"
        ) from exc

    sdk_key = f"sdk-manifests/{asset_id}.json"
    try:
        sdk_manifest_key = sdk_key if b2.exists("vault", sdk_key) else None
    except Exception:
        sdk_manifest_key = None

    parents = []
    if row.get("parent_asset"):
        parent = index.get_asset(row["parent_asset"])
        if parent:
            parents.append(verify.asset_summary(parent))
    children = [
        verify.asset_summary(c) for c in index.children_of(asset_id, status="sealed")
    ]
    discarded = [
        verify.asset_summary(c) for c in index.children_of(asset_id, status="discarded")
    ]

    return {
        "asset": verify.asset_summary(row),
        "manifest": manifest,
        "sdk_manifest_key": sdk_manifest_key,
        "receipts": verify.load_receipts(row["run_id"]),
        "lineage": {"parents": parents, "children": children, "discarded": discarded},
        "anchor": merkle.proof_for(row["manifest_key"]),
    }


# --- verify -----------------------------------------------------------------

@app.post("/api/verify")
async def verify_upload(request: Request, file: UploadFile) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    try:
        verify.check_rate_limit(client_ip)
        # Read at most cap+1 bytes; the extra byte proves an oversize upload
        # without buffering arbitrarily more (R6: capped, never stored).
        data = await file.read(verify.MAX_VERIFY_BYTES + 1)
        result = await anyio.to_thread.run_sync(
            verify.verify_bytes, data, file.content_type
        )
        return result
    except verify.VerifyRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# --- export -----------------------------------------------------------------

@app.post("/api/export", status_code=202)
def create_export() -> dict[str, str]:
    _require_or_503("b2_assets", "b2_vault", "b2_state")
    if index.count_assets() == 0:
        raise HTTPException(
            status_code=409,
            detail="Nothing in the vault yet — generate an asset before exporting.",
        )
    return {"export_id": export.start_export()}


@app.get("/api/exports/{export_id}")
def export_status(export_id: str) -> dict[str, Any]:
    st = export.get_status(export_id)
    if st is None:
        raise HTTPException(status_code=404, detail=f"Unknown export {export_id!r}")
    out: dict[str, Any] = {"status": st["status"]}
    if st["status"] == "ready":
        out["download_url"] = f"/api/exports/{export_id}/download"
    if st["status"] == "failed" and st.get("error"):
        out["error"] = st["error"]
    return out


@app.get("/api/exports/{export_id}/download")
def export_download(export_id: str):
    st = export.get_status(export_id)
    if st is None:
        raise HTTPException(status_code=404, detail=f"Unknown export {export_id!r}")
    if st["status"] != "ready":
        raise HTTPException(
            status_code=409, detail=f"Export {export_id} is {st['status']}, not ready."
        )
    try:
        stream = b2.stream("state", export.state_key(export_id))
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StreamingResponse(
        stream,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="litmus-{export_id}.zip"'
        },
    )


# --- anchors ----------------------------------------------------------------

@app.post("/api/anchor")
def force_anchor() -> dict[str, Any]:
    _require_or_503("b2_vault")
    try:
        anchor = merkle.anchor_new()
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if anchor is None:
        raise HTTPException(
            status_code=409, detail="Nothing new to anchor since the last batch."
        )
    return {
        "batch": anchor["batch"],
        "merkle_root": anchor["merkle_root"],
        "leaf_count": anchor["leaf_count"],
    }


@app.get("/api/anchors")
def list_anchors() -> dict[str, Any]:
    try:
        return {"anchors": merkle.list_anchors()}
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# --- SPA --------------------------------------------------------------------

if WEB_DIST.is_dir():
    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="spa-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (WEB_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(WEB_DIST.resolve())
        ):
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
else:

    @app.get("/", include_in_schema=False)
    def root_placeholder() -> JSONResponse:
        return JSONResponse(
            {
                "service": "litmus",
                "note": "web/dist not built yet — API is live under /api",
                "health": "/api/health",
            }
        )
