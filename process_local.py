#!/usr/bin/env python3
"""
Process a local WAV file into normalized 16k mono segments and upload to GCS.
Produces a JSON payload compatible with the Node manual import endpoint.

Usage (PowerShell):
  python process_local.py --source-id <AudioSourceId> --wav "./data/sources/<source_id>.wav" --chunk-seconds 20
  # Dry-run (no upload) just to see chunks locally
  python process_local.py --source-id test --wav ./data/sources/test.wav --chunk-seconds 20 --no-upload
  # Upload and clean up chunks after
  python process_local.py --source-id test --wav ./data/sources/test.wav --chunk-seconds 20 --clean

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


async def process_local(source_id: str, wav_path: Path, chunk_seconds: int, upload: bool, clean: bool = False) -> dict:
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    # Working directory alongside the wav
    workdir = Path("./data/tmp") / f"manual_{source_id}"
    workdir.mkdir(parents=True, exist_ok=True)

    logging.info("[local] probing duration for %s", wav_path)
    total_dur = await ffprobe_duration(settings.ffprobe_path, wav_path)

    # Check if chunks already exist
    existing_chunks = sorted(workdir.glob("chunk_*.wav"))
    
    if existing_chunks:
        logging.info("[local] ✓ Found %d existing chunks, skipping normalization & chunking", len(existing_chunks))
        chunks_local = existing_chunks
        
        # Load durations from metadata file if it exists
        metadata_file = workdir / "chunk_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
                actual_durations = metadata.get("durations", [])
                logging.info("[local] ✓ Loaded chunk durations from metadata")
        else:
            # Fallback: probe each chunk for duration
            logging.info("[local] Probing duration for each existing chunk...")
            actual_durations = []
            for chunk in chunks_local:
                dur = await ffprobe_duration(settings.ffprobe_path, chunk)
                actual_durations.append(dur if dur else chunk_seconds)
    else:
        logging.info("[local] normalizing and chunking: chunk_seconds=%s", chunk_seconds)
        chunks_local, actual_durations = await normalize_and_chunk(
            settings.ffmpeg_path, wav_path, workdir, chunk_seconds
        )
        
        # Save metadata for future runs
        metadata_file = workdir / "chunk_metadata.json"
        with open(metadata_file, "w") as f:
            json.dump({"durations": actual_durations}, f)
        logging.info("[local] ✓ Saved chunk metadata")

    logging.info("[local] %d chunks ready", len(chunks_local))

    # Upload or prepare local URIs
    uris: List[str] = []
    if upload:
        logging.info("\n" + "="*60)
        logging.info("UPLOADING CHUNKS TO GCS")
        logging.info("="*60)
        logging.info(f"Destination: gs://{settings.gcs_bucket}/audio_chunks/{source_id}/")
        logging.info(f"Total chunks: {len(chunks_local)}\n")
        
        for idx, p in enumerate(chunks_local, start=1):
            object_name = f"audio_chunks/{source_id}/{p.name}"
            
            logging.info(f"[{idx}/{len(chunks_local)}] {p.name}")
            uri = upload_file(str(p), object_name, content_type="audio/wav")
            uris.append(uri)
    else:
        logging.info("[local] Skipping upload (--no-upload flag set)")
        for p in chunks_local:
            uris.append(str(p.resolve()))

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
    logging.info("\n[local] ✓ Wrote output to: %s", outfile)

    # Clean up chunks if requested
    if clean and upload:
        logging.info("\n" + "="*60)
        logging.info("CLEANING UP CHUNKS")
        logging.info("="*60)
        try:
            import shutil
            if workdir.exists():
                shutil.rmtree(workdir)
                logging.info("✓ Deleted: %s", workdir)
                logging.info("✓ Cleanup complete!")
        except Exception as e:
            logging.warning("⚠️  Cleanup failed: %s", e)

    return payload


def main():
    parser = argparse.ArgumentParser(description="Normalize, chunk, and upload a local WAV to GCS.")
    parser.add_argument("--source-id", required=True, help="AudioSource.id to use for storage path and DB linking")
    parser.add_argument("--wav", required=True, help="Path to local WAV file (from yt-dlp or elsewhere)")
    parser.add_argument("--chunk-seconds", type=int, default=settings.chunk_seconds, help="Chunk length in seconds (default from settings)")
    parser.add_argument("--no-upload", action="store_true", help="Do not upload to GCS; keep chunks locally only")
    parser.add_argument("--clean", action="store_true", help="Delete chunks after successful upload")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    source_id = args.source_id
    wav_path = Path(args.wav)
    chunk_seconds = args.chunk_seconds
    upload = not args.no_upload
    clean = args.clean

    if upload and not settings.gcs_bucket:
        raise SystemExit("GCS_BUCKET is not configured; set it in .env or use --no-upload")

    if clean and not upload:
        logging.warning("⚠️  --clean flag ignored (--no-upload is set)")
        clean = False

    payload = asyncio.run(process_local(source_id, wav_path, chunk_seconds, upload, clean))
    print("\n" + "="*60)
    print("PROCESSING COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()