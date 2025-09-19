import asyncio
from uuid import UUID
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

from .config import settings
from .models import IngestYouTubeRequest, IngestResponse, JobStatusPayload, WebhookPayload, ChunkMeta
from .jobs import job_store
from .pipeline import download_youtube, ffprobe_duration, normalize_and_chunk
from .storage import upload_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(title="KACCP Media Worker", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest/youtube", response_model=IngestResponse, status_code=202)
async def ingest_youtube(payload: IngestYouTubeRequest):
    if not settings.gcs_bucket:
        raise HTTPException(status_code=500, detail="GCS_BUCKET not configured")
    chunk_seconds = payload.chunk_seconds or settings.chunk_seconds
    logging.info("[ingest] request source_id=%s url=%s chunk_seconds=%s", payload.source_id, payload.url, chunk_seconds)
    # Prefer request webhook_url; otherwise fall back to DEFAULT_WEBHOOK_URL if set
    webhook_url = payload.webhook_url or settings.default_webhook_url
    job_id = job_store.create(payload.source_id, chunk_seconds, webhook_url)
    # Start background processing
    asyncio.create_task(_run_job(job_id, payload.url))
    return IngestResponse(job_id=job_id)


@app.get("/jobs/{job_id}", response_model=JobStatusPayload)
async def get_job(job_id: UUID):
    payload = job_store.get_payload(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="job not found")
    return payload


async def _run_job(job_id: UUID, url: str):
    # Create a temp working directory per job
    workdir_root = Path("./data/tmp")
    workdir_root.mkdir(parents=True, exist_ok=True)
    workdir = workdir_root / str(job_id)
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        job_store.set_running(job_id, "downloading from YouTube")
        logging.info("[job %s] start; url=%s", job_id, url)
        # Download
        downloaded = await download_youtube(settings.yt_dlp_path, url, workdir)
        logging.info("[job %s] download done: %s", job_id, downloaded)
        job_store.update_progress(job_id, 0.10, "download complete")
        # Duration for progress estimates
        total_dur = await ffprobe_duration(settings.ffprobe_path, downloaded)
        # Resolve chunk seconds from job store or fallback
        js = job_store._jobs.get(job_id)
        chunk_seconds = js.chunk_seconds if js and js.chunk_seconds else settings.chunk_seconds

        job_store.update_progress(job_id, 0.15, "normalizing audio")
        chunks_local = await normalize_and_chunk(settings.ffmpeg_path, downloaded, workdir, chunk_seconds)
        logging.info("[job %s] chunking done: %d chunks", job_id, len(chunks_local))
        job_store.update_progress(job_id, 0.50, "chunking complete; uploading")

        # Upload to GCS
        uploaded_uris: List[str] = []
        total = len(chunks_local)
        for idx, p in enumerate(chunks_local, start=1):
            js2 = job_store._jobs.get(job_id)
            src_id = js2.source_id if js2 else "unknown_source"
            object_name = f"audio_chunks/{src_id}/{p.name}"
            uri = upload_file(str(p), object_name, content_type="audio/wav")
            uploaded_uris.append(uri)
            # Progress between 0.1..0.99 as we upload
            prog = 0.1 + 0.89 * (idx / max(1, total))
            job_store.update_progress(job_id, prog, f"uploaded {idx}/{total}")
            if idx % 5 == 0 or idx == total:
                logging.info("[job %s] uploaded %d/%d -> %s", job_id, idx, total, uri)

        job_store.complete(job_id, uploaded_uris, total_dur, chunk_seconds)

        # Build chunk metadata for webhook consumers (Node/Prisma)
        chunks_meta = []
        for i, uri in enumerate(uploaded_uris, start=1):
            start_sec = (i - 1) * chunk_seconds
            # If we know total duration, compute the last chunk actual duration
            if total_dur is not None:
                end_sec = min(int(start_sec + chunk_seconds), int(total_dur))
            else:
                end_sec = start_sec + chunk_seconds
            duration_sec = max(0, end_sec - start_sec)
            chunks_meta.append(ChunkMeta(index=i, startSec=start_sec, endSec=end_sec, durationSec=duration_sec, gcsUri=uri))

        await _maybe_webhook(job_id, success=True, chunks=uploaded_uris, total_dur=total_dur, chunk_seconds=chunk_seconds, chunks_meta=chunks_meta)

    except Exception as e:
        job_store.fail(job_id, str(e))
        await _maybe_webhook(job_id, success=False, error=str(e))
    finally:
        # Best-effort cleanup
        try:
            for p in workdir.glob("**/*"):
                try:
                    p.unlink()
                except Exception:
                    pass
            for p in sorted(workdir.glob("**/*"), reverse=True):
                try:
                    p.rmdir()
                except Exception:
                    pass
        except Exception:
            pass


async def _maybe_webhook(job_id: UUID, success: bool, chunks: Optional[List[str]] = None, error: Optional[str] = None, total_dur: Optional[float] = None, chunk_seconds: Optional[int] = None, chunks_meta: Optional[List[ChunkMeta]] = None):
    job = job_store._jobs.get(job_id)
    if not job or not job.webhook_url:
        return
    payload = WebhookPayload(
        job_id=job_id,
        source_id=job.source_id,
        status="completed" if success else "failed",
        chunks=chunks,
        error=error,
        meta={
            "total_duration_sec": total_dur,
            "chunk_seconds": chunk_seconds,
        },
        totalDurationSeconds=int(total_dur) if total_dur is not None else None,
        chunkSeconds=chunk_seconds,
        originalUri=None,
        chunksMeta=chunks_meta,
    )
    headers = {"Content-Type": "application/json"}
    if settings.webhook_auth_token:
        headers["Authorization"] = f"Bearer {settings.webhook_auth_token}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(job.webhook_url, json=payload.model_dump(), headers=headers)
    except Exception:
        # Silent fail on webhook; status still holds in store
        pass
