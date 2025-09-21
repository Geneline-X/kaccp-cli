#!/usr/bin/env python3
"""
Process a local WAV file into normalized 16k mono segments and upload to GCS.
Produces a JSON payload compatible with the Node manual import endpoint.

Usage (PowerShell):
  python process_local.py --source-id <AudioSourceId> --wav "./data/sources/<source_id>.wav" --chunk-seconds 20
  # Dry-run (no upload) just to see chunks locally
  python process_local.py --source-id test --wav ./data/sources/test.wav --chunk-seconds 20 --no-upload

Output: JSON printed to stdout and also written to ./data/output/<source_id>_chunks.json
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

from app.config import settings
from app.pipeline import ffprobe_duration, normalize_and_chunk
from app.storage import upload_file


async def process_local(source_id: str, wav_path: Path, chunk_seconds: int, upload: bool) -> dict:
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    # Working directory alongside the wav
    workdir = Path("./data/tmp") / f"manual_{source_id}"
    workdir.mkdir(parents=True, exist_ok=True)

    logging.info("[local] probing duration for %s", wav_path)
    total_dur = await ffprobe_duration(settings.ffprobe_path, wav_path)

    logging.info("[local] normalizing and chunking: chunk_seconds=%s", chunk_seconds)
    # Now receives both chunks and their actual durations
    chunks_local, actual_durations = await normalize_and_chunk(settings.ffmpeg_path, wav_path, workdir, chunk_seconds)

    logging.info("[local] %d chunks ready", len(chunks_local))

    # Upload or prepare local URIs
    uris: List[str] = []
    for p in chunks_local:
        if upload:
            object_name = f"audio_chunks/{source_id}/{p.name}"
            uri = upload_file(str(p), object_name, content_type="audio/wav")
        else:
            uri = str(p.resolve())
        uris.append(uri)

    # Build chunksMeta using the actual durations from chunking
    chunks_meta = []
    current_start = 0.0
    
    for i, (uri, actual_duration) in enumerate(zip(uris, actual_durations), start=1):
        end_sec = current_start + actual_duration
        
        chunks_meta.append({
            "index": i,
            "startSec": int(round(current_start)),
            "endSec": int(round(end_sec)),
            "durationSec": int(round(actual_duration)),
            "gcsUri": uri if upload else None,
            "localPath": None if upload else uri,
        })
        
        current_start = end_sec

    payload = {
        "sourceId": source_id,
        "totalDurationSeconds": int(round(total_dur)) if total_dur is not None else None,
        "chunkSeconds": chunk_seconds,
        "chunksMeta": chunks_meta,
    }

    # Write to file under data/output
    outdir = Path("./data/output")
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / f"{source_id}_chunks.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logging.info("[local] wrote %s", outfile)

    return payload


def main():
    parser = argparse.ArgumentParser(description="Normalize, chunk, and upload a local WAV to GCS.")
    parser.add_argument("--source-id", required=True, help="AudioSource.id to use for storage path and DB linking")
    parser.add_argument("--wav", required=True, help="Path to local WAV file (from yt-dlp or elsewhere)")
    parser.add_argument("--chunk-seconds", type=int, default=settings.chunk_seconds, help="Chunk length in seconds (default from settings)")
    parser.add_argument("--no-upload", action="store_true", help="Do not upload to GCS; keep chunks locally only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    source_id = args.source_id
    wav_path = Path(args.wav)
    chunk_seconds = args.chunk_seconds
    upload = not args.no_upload

    if upload and not settings.gcs_bucket:
        raise SystemExit("GCS_BUCKET is not configured; set it in .env or use --no-upload")

    payload = asyncio.run(process_local(source_id, wav_path, chunk_seconds, upload))
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
