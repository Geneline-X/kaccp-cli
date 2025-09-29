# KACCP Media Processing – Local CLI Usage

This doc shows how to use the local/manual workflow to build your audio dataset:

- Download audio from YouTube with `yt-dlp`.
- Normalize, chunk, and (optionally) upload chunks to Google Cloud Storage (GCS) with `process_local.py`.
- Import the resulting JSON into your Node app to create `AudioSource` and `AudioChunk` rows for the transcriber UI.

If you prefer an always-on service, you can run the FastAPI worker in `app/`, but the steps below assume a manual, low-ops flow.

## Prerequisites
- Python 3.11+
- ffmpeg/ffprobe installed and on PATH (or set `FFMPEG_PATH`/`FFPROBE_PATH` in `.env`)
- `yt-dlp` installed on PATH (`pip install yt-dlp`)
- (If uploading) GCP service account with Storage write access to your bucket

## Environment (.env)
Set these in `.env` at project root:

```
GCS_BUCKET=kaccp
# Option A: Inline JSON (local/dev)
GCS_SERVICE_ACCOUNT_JSON='{"type":"service_account", ... }'
# Option B: Path to JSON file
# GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\sa.json

# Optional tool paths if not on PATH
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe
```

## Step 1: Download source audio with yt-dlp
Pick a `source_id` that will be the `AudioSource.id` in your Node/Prisma DB (recommended to use a real cuid from your app so paths align exactly).

```powershell
yt-dlp -f bestaudio/best -x --audio-format wav --no-playlist --retries 2 --socket-timeout 20 --force-ipv4 \
  -o "./data/sources/<source_id>.%(ext)s" "https://www.youtube.com/watch?v=<VIDEO_ID>"
```

This produces: `data/sources/<source_id>.wav`

## Step 2: Normalize, chunk, and upload to GCS
Use the provided script which reuses the pipeline in `app/pipeline.py` and uploader in `app/storage.py`:

```powershell
python process_local.py --source-id <source_id> --wav ./data/sources/<source_id>.wav
```

- Without uploading (dry-run): add `--no-upload` to keep chunks locally and inspect them first.
- Output:
  - Chunks uploaded to: `gs://kaccp/audio_chunks/<source_id>/chunk_XXXX.wav` (unless `--no-upload`)
  - JSON written to: `data/output/<source_id>_chunks.json` and printed to stdout

Example JSON (truncated):

```json
{
  "sourceId": "cmfq71dna000f6zih6jdmcclv",
  "totalDurationSeconds": 230,
  "chunkSeconds": 20,
  "chunksMeta": [
    {
      "index": 1,
      "startSec": 0,
      "endSec": 20,
      "durationSec": 20,
      "gcsUri": "gs://kaccp/audio_chunks/cmfq71dna000f6zih6jdmcclv/chunk_0001.wav"
    }
  ]
}
```

## Step 3: Verify uploads in GCS

```powershell
gsutil ls gs://kaccp/audio_chunks/<source_id>/
```

If you don’t use `gsutil`, you can also verify by listing via the GCS Console or a small Node/Python snippet with the GCS client.

## Quick commands (copy–paste)

Set up environment and install deps (Windows PowerShell):

```powershell
# Optional: create and activate venv
python -m venv .venv
.\.venv\Scripts\Activate

# Install Python dependencies
pip install -r requirements.txt
```

Download a YouTube video’s best audio to WAV using a chosen source_id (match your Prisma AudioSource.id):

```powershell
# Replace <source_id> and <VIDEO_ID>
yt-dlp -f bestaudio/best -x --audio-format wav --no-playlist --retries 2 --socket-timeout 20 --force-ipv4 \
  -o "./data/sources/<source_id>.%(ext)s" "https://www.youtube.com/watch?v=<VIDEO_ID>"
```

Normalize, chunk into 20s, and upload to GCS (writes JSON to data/output/):

```powershell
python process_local.py --source-id <source_id> --wav ./data/sources/<source_id>.wav --chunk-seconds 20
```

Dry-run locally (no uploads, chunks remain on disk under data/tmp/):

```powershell
python process_local.py --source-id <source_id> --wav ./data/sources/<source_id>.wav --chunk-seconds 20 --no-upload
```

Verify in GCS with gsutil (optional):

```powershell
gsutil ls gs://kaccp/audio_chunks/<source_id>/
```

## Step 4: Import into the Node app
Create a simple API endpoint in your Node/Next app (e.g., `POST /api/manual-import-chunks`) that accepts the JSON produced in Step 2 and performs:

- Create/Update `AudioSource` with:
  - `id = sourceId`
  - `totalDurationSeconds`, `status = READY`
- Upsert `AudioChunk` for each `chunksMeta[i]` with:
  - `sourceId`, `index`, `startSec`, `endSec`, `durationSec`, `storageUri = gcsUri`, `status = AVAILABLE`

After that, your transcriber UI can request chunks for a given `sourceId`, and your Node app should generate signed URLs for each `storageUri` using `@google-cloud/storage`.

## Serving to transcribers
- Generate a signed URL per chunk URI (gs://…) in Node for secure HTTP access (time-limited).
- Do not make the bucket public unless you truly want public access.

## Troubleshooting
- No chunks appear in GCS:
  - Ensure `.env` has `GCS_BUCKET` set and valid credentials (inline JSON or `GOOGLE_APPLICATION_CREDENTIALS`).
  - The service account must have Storage write permissions for the bucket.
- ffmpeg/ffprobe not found:
  - Install them and/or set `FFMPEG_PATH` / `FFPROBE_PATH` in `.env`.
- Audio looks too quiet/loud or stereo:
  - The pipeline applies loudness normalization and converts to mono 16 kHz. Adjust filters in `app/pipeline.py` if needed.
- Use a different chunk length:
  - Pass `--chunk-seconds <N>` to `process_local.py` (default 20).

---

# Appendix – Git & Repo Hygiene (previous guide)

This section preserves the previous Git workflow tips for convenience.

## Prerequisites
- Git installed
- A GitHub account and an existing repo (or permission to create one)
- Windows PowerShell or your preferred terminal

## Project Structure Highlights
- `.gitignore` is configured to exclude:
  - Environment files: `.env`, `.env.*` (examples like `.env.example` are allowed)
  - Data directories: `data/`, `uploads/`, `media/`, `storage/`
  - Build artifacts and caches for Python/Node/Rust
  - Logs and IDE/OS clutter
- If your pipeline generates audio chunks, they should live under `data/chunks/audio_chunks/` and will be ignored by Git.

## Environment Variables
- Keep secrets in `.env` (ignored by Git).
- Optionally create `.env.example` with placeholder keys for collaborators:
  ```env
  API_KEY=your_key_here
  SERVICE_URL=http://localhost:8000
  # Add other required variables here
  ```

## First-Time Git Setup
1. Initialize the repository (if not already):
   ```powershell
   git init
   ```
2. Add a remote (replace with your repo URL):
   ```powershell
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   ```
3. Verify remotes:
   ```powershell
   git remote -v
   ```

## Verify .gitignore is Working
- Check current status:
  ```powershell
  git status
  ```
- Files like `.env` and folders like `data/` should appear under “Untracked files” ONLY if they were not already committed previously. If they are already tracked, see next section.

## Stop Tracking Files Already Committed by Mistake
If you previously committed sensitive or large files (e.g., `.env`, `data/`):

1. Remove them from the index while keeping local copies:
   ```powershell
   git rm --cached .env
   git rm -r --cached data
   ```
   Add other paths as needed (e.g., `uploads/`, `storage/`).

2. Commit the removal and the updated `.gitignore`:
   ```powershell
   git add .gitignore
   git commit -m "chore: stop tracking secrets/data and update .gitignore"
   ```

3. Push the changes:
   ```powershell
   git push -u origin main
   ```
   If your default branch is `master` or something else, substitute accordingly.

Note: If secrets were pushed to a public repository, rotate them immediately and consider using GitHub’s secret scanning tools or history rewrite tools (e.g., `git filter-repo`) to purge history.

## Normal Commit and Push Workflow
1. Check what will be committed:
   ```powershell
   git status
   ```
2. Stage changes:
   ```powershell
   git add <files-or-folders>
   # or add everything that isn't ignored
   git add .
   ```
3. Commit with a clear message:
   ```powershell
   git commit -m "feat: add new endpoint for X"
   ```
4. Push to GitHub:
   ```powershell
   git push
   ```

## Branching Workflow (Recommended)
- Create a feature branch:
  ```powershell
  git checkout -b feat/new-feature
  ```
- Push the branch and open a Pull Request on GitHub:
  ```powershell
  git push -u origin feat/new-feature
  ```

## Common CLI Commands Cheat Sheet
- Show current branch and changes:
  ```powershell
  git status
  ```
- View commit history (last 10):
  ```powershell
  git log -n 10 --oneline
  ```
- See what changed in working tree:
  ```powershell
  git diff
  ```
- Discard local changes in a file:
  ```powershell
  git checkout -- path\to\file
  ```
- Pull latest from default branch:
  ```powershell
  git pull
  ```

## Safety Tips
- Never commit real secrets. Use `.env` locally and add `.env.example` for documentation.
- Keep `data/` and other large/generated assets out of Git; rely on cloud storage or build pipelines instead.
- If you accidentally commit secrets, rotate them and remove them from Git history.

## Troubleshooting
- `.env` or `data/` keep showing up in commits:
  - Ensure the entries exist in `.gitignore`.
  - If already tracked, run `git rm --cached` as described above.
- Pushing to the wrong branch:
  - Check your branch with `git branch --show-current`.
  - Push with `git push -u origin <branch>`.

---
If you want, I can run the safe untracking and status commands for you from the terminal. Just say “run the git cleanup steps.”
