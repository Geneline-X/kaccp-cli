import asyncio
import os
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
import logging
from .config import settings
import contextlib


async def run_cmd_stream(cmd: list[str], timeout: Optional[int] = None) -> Tuple[int, str, str]:
    """Run a command, streaming stdout/stderr to logs in real time.
    Returns (returncode, stdout_text, stderr_text)."""
    logging.info("exec: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_chunks: List[bytes] = []
    stderr_chunks: List[bytes] = []

    async def _read_stream(stream, is_err: bool):
        while True:
            line = await stream.readline()
            if not line:
                break
            try:
                txt = line.decode(errors="ignore").rstrip()
            except Exception:
                txt = str(line)
            if is_err:
                logging.debug("stderr| %s", txt)
                stderr_chunks.append(line)
            else:
                logging.debug("stdout| %s", txt)
                stdout_chunks.append(line)

    reader_out = asyncio.create_task(_read_stream(proc.stdout, is_err=False))
    reader_err = asyncio.create_task(_read_stream(proc.stderr, is_err=True))

    try:
        if timeout and timeout > 0:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        else:
            await proc.wait()
    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            proc.kill()
        logging.warning("process timeout after %ss; killed: %s", timeout, cmd[0])
        raise
    finally:
        with contextlib.suppress(Exception):
            await reader_out
        with contextlib.suppress(Exception):
            await reader_err

    out = b"".join(stdout_chunks).decode(errors="ignore")
    err = b"".join(stderr_chunks).decode(errors="ignore")
    if err:
        logging.debug("stderr_tail: %s", err[-4000:])
    return proc.returncode, out, err


async def download_youtube(yt_dlp_path: str, url: str, out_dir: Path) -> Path:
    logging.info("[download] start url=%s", url)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = str(out_dir / "download.%(ext)s")

    base_cmd = [
        yt_dlp_path,
        "-f", "bestaudio/best",
        "-x",
        "--audio-format", "wav",
        "-o", output_pattern,
    ]
    # Tuning flags
    if settings.yt_no_playlist:
        base_cmd += ["--no-playlist"]
    base_cmd += ["--retries", str(settings.yt_retries)]
    base_cmd += ["--socket-timeout", str(settings.yt_socket_timeout)]
    if settings.yt_force_ipv4:
        base_cmd += ["--force-ipv4"]
    if settings.yt_extra_args:
        # naive split on space; for complex args, set via env with quotes
        base_cmd += settings.yt_extra_args.split()
    base_cmd.append(url)

    last_err = None
    attempts = max(1, min(10, settings.yt_retries))
    for attempt in range(1, attempts + 1):
        logging.info("[download] attempt %d/%d", attempt, attempts)
        try:
            # enforce an overall timeout per attempt
            code, out, err = await run_cmd_stream(base_cmd, timeout=settings.yt_timeout_seconds)
            if code == 0:
                # Find resulting wav
                for p in out_dir.iterdir():
                    if p.is_file() and p.suffix.lower() == ".wav":
                        logging.info("[download] done file=%s", p)
                        return p
                last_err = "yt-dlp reported success but output wav not found"
            else:
                last_err = f"yt-dlp exit={code} err_tail={(err or '')[-4000:]}"
                logging.warning("[download] failed: %s", last_err)
        except asyncio.TimeoutError:
            last_err = f"yt-dlp timed out after {settings.yt_timeout_seconds}s"
            logging.warning("[download] timeout: %s", last_err)

        # small backoff before retry
        await asyncio.sleep(2 * attempt)

    raise RuntimeError(f"download failed after {attempts} attempts: {last_err}")


async def ffprobe_duration(ffprobe_path: str, media_path: Path) -> Optional[float]:
    logging.info("[probe] duration file=%s", media_path)
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    code, out, _ = await run_cmd_stream(cmd, timeout=60)
    if code == 0:
        try:
            logging.info("[probe] duration_ok seconds=%s", out.strip())
            return float(out.strip())
        except Exception:
            return None
    return None


async def normalize_and_chunk(
    ffmpeg_path: str,
    input_media: Path,
    output_dir: Path,
    chunk_seconds: int,
) -> List[Path]:
    logging.info("[normalize] start input=%s", input_media)
    output_dir.mkdir(parents=True, exist_ok=True)
    norm_wav = output_dir / "normalized.wav"

    # Normalize to mono 16k with loudnorm
    cmd_norm = [
        ffmpeg_path,
        "-y",
        "-i", str(input_media),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        str(norm_wav),
    ]
    code, _, err = await run_cmd_stream(cmd_norm, timeout=600)
    if code != 0:
        raise RuntimeError(f"ffmpeg normalization failed: {err}")
    logging.info("[normalize] done output=%s", norm_wav)

    # Segment
    pattern = output_dir / "chunk_%04d.wav"
    logging.info("[segment] start seconds=%s pattern=%s", chunk_seconds, pattern)
    cmd_seg = [
        ffmpeg_path,
        "-y",
        "-i", str(norm_wav),
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-c", "copy",
        "-reset_timestamps", "1",
        str(pattern),
    ]
    code, _, err = await run_cmd_stream(cmd_seg, timeout=600)
    if code != 0:
        raise RuntimeError(f"ffmpeg segmenting failed: {err}")

    chunks: List[Path] = []
    for p in sorted(output_dir.iterdir()):
        if p.is_file() and p.name.startswith("chunk_") and p.suffix.lower() == ".wav":
            chunks.append(p)
    if not chunks:
        raise RuntimeError("no chunks produced")
    logging.info("[segment] done count=%d", len(chunks))
    return chunks
