# KACCP Media Processing

[![Build Status](https://github.com/your-org/kaccp-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/kaccp-cli/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

A CLI tool developed by **[Geneline-X](https://geneline-x.net)** for downloading, normalizing, chunking, and optionally uploading audio from YouTube to Google Cloud Storage (GCS) for the KACCP transcription platform. Supports both local/manual workflows and future always-on worker (FastAPI) workflows.

---

## Table of Contents

- [About](#about)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Installation](#installation)
- [Usage / CLI Commands](#usage--cli-commands)
- [Folder / Project Structure](#folder--project-structure)
- [How It Works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## About

**KACCP Media Processing** is a Python CLI tool developed and maintained by **[Geneline-X](https://geneline-x.net)** for the Krio Audio Corpus Collection Platform (KACCP). It streamlines audio preparation for transcription by automating the download, normalization, chunking, and (optionally) uploading of YouTube audio to Google Cloud Storage. It also generates JSON metadata compatible with Node/Next.js apps using Prisma for seamless import into the transcription workflow.

**Audience:**

- Developers and admins managing KACCP datasets
- Contributors preparing audio for transcription
- Researchers building low-resource language corpora

**Use Case:**

- Crowdsourcing audio for transcription in Krio (and future languages)
- Building high-quality datasets for NLP and speech research
- Managing workflow, quality, and secure audio uploads

---

## Features

- Download audio from YouTube via [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Normalize audio to mono 16kHz WAV using [ffmpeg](https://ffmpeg.org/)
- Smart chunking of audio into configurable segment lengths
- Optional upload of audio chunks to Google Cloud Storage (GCS)
- Generates JSON metadata for Node/Next.js apps (Prisma AudioSource/AudioChunk)
- Dry-run mode for local testing (no upload)
- Supports both manual CLI and always-on FastAPI worker modes

---

## Prerequisites

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) and [ffprobe](https://ffmpeg.org/ffprobe.html) installed and on PATH (or specify via `.env`)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed
- Google Cloud service account with Storage write access (if uploading to GCS)

---

## Environment Setup

Create a `.env` file at the project root with the following variables:

```env
GCS_BUCKET=kaccp
# Option A: Inline JSON credentials
GCS_SERVICE_ACCOUNT_JSON='{"type":"service_account", ... }'
# Option B: Path to JSON file
# GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\sa.json

# Optional: override tool paths if not on PATH
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe
```

Other optional variables:

- `CHUNK_SECONDS` – Default chunk length (default: 20)
- `DEFAULT_WEBHOOK_URL` – For FastAPI worker mode
- `WEBHOOK_AUTH_TOKEN` – For webhook authentication

---

## Installation

```powershell
# Clone the repository
git clone https://github.com/your-org/kaccp-cli.git
cd kaccp-cli

# (Optional) Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate

# Install Python dependencies
pip install -r requirements.txt
```

---

## Usage / CLI Commands

### 1. Download YouTube Audio

```powershell
yt-dlp -f bestaudio/best -x --audio-format wav --no-playlist --retries 2 --socket-timeout 20 --force-ipv4 `
  -o "./data/sources/<source_id>.%(ext)s" "https://www.youtube.com/watch?v=<VIDEO_ID>"
```

### 2. Normalize, Chunk, and (Optionally) Upload

```powershell
python process_local.py --source-id <source_id> --wav ./data/sources/<source_id>.wav --chunk-seconds 20
```

- Add `--no-upload` for a dry-run (chunks remain local, not uploaded).

### 3. Output

- Chunks uploaded to: `gs://<GCS_BUCKET>/audio_chunks/<source_id>/chunk_XXXX.wav`
- JSON metadata written to: `data/output/<source_id>_chunks.json` and printed to stdout

### 4. Import JSON into Node App

- Use the generated JSON to create/update `AudioSource` and `AudioChunk` records in your Node/Next.js app.

---

## Folder / Project Structure

```
kaccp-cli/
├── app/
│   ├── __init__.py         # Package marker
│   ├── config.py           # Environment/config management
│   ├── jobs.py             # In-memory job store for FastAPI worker
│   ├── main.py             # FastAPI worker entrypoint
│   ├── models.py           # Pydantic models for API and metadata
│   ├── pipeline.py         # Audio processing pipeline (normalize, chunk)
│   ├── storage.py          # GCS upload logic
├── process_local.py        # CLI script for local/manual processing
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker build for FastAPI worker
├── docker-compose.yml      # Docker Compose for local dev
├── .gitignore              # Git ignore rules
├── README.md               # Project documentation
```

---

## How It Works

1. **Download** – Fetch best audio from YouTube using `yt-dlp`.
2. **Normalize** – Convert to mono, 16kHz WAV and loudness-normalize via ffmpeg.
3. **Chunk** – Split audio into segments (default 20s).
4. **Upload** – Optional upload to GCS.
5. **Metadata** – JSON describing all chunks is generated.
6. **Import** – Use JSON to upsert `AudioSource` and `AudioChunk` in your database.
7. **Optional** – Run as an always-on FastAPI worker for API-driven ingestion.

---

## Troubleshooting

- **ffmpeg/ffprobe not found** – Ensure installed or set `FFMPEG_PATH`/`FFPROBE_PATH` in `.env`.
- **GCS upload fails** – Check `GCS_BUCKET` and credentials; ensure service account has write permissions.
- **No chunks produced** – Verify WAV file path/format; check pipeline logs.
- **Audio issues** – Adjust filters in `app/pipeline.py` if needed.
- **Debugging** – Use `--no-upload` to test locally.

---

## Contributing

1. **Fork** and create a branch:

```powershell
git checkout -b feat/your-feature
```

2. **Commit** changes:

```powershell
git add .
git commit -m "feat: add your feature"
```

3. **Push** and open a Pull Request.

**Git Hygiene:**

- Do not commit large/generated files (`data/`, audio chunks)
- Keep secrets in `.env` (never commit real credentials)
- Add `.env.example` for documentation

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgements

- Developed and maintained by **[Geneline-X](https://geneline-x.net)**
- [Python](https://www.python.org/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/)
- [Google Cloud Storage](https://cloud.google.com/storage)
- All contributors and the open-source community

---
## Support
For questions or support, contact [Geneline-X](mailto:contact@geneline-x.net)
