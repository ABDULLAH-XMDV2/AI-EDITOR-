# Reelcut — AI Auto Video Editor

A self-hosted, fully open-source "CapCut AI (basic)" clone. Upload a video,
and a local AI pipeline automatically detects scenes, removes silence,
tracks faces, auto-crops/zooms, corrects color, stabilizes, normalizes
audio, generates and burns in subtitles, optionally mixes background
music, applies smart transitions, and exports 720p + 1080p files. No paid
APIs, no external editing services — everything runs on your own machine.

## Folder structure

```
/project
├── frontend/                 # HTML5 + Tailwind + vanilla JS (no framework)
│   ├── index.html            # Landing page
│   ├── upload.html           # Upload + processing + preview + download flow
│   ├── dashboard.html        # Stats + job history
│   ├── css/style.css
│   └── js/{main,upload,dashboard}.js
│
├── backend/
│   ├── main.py                # FastAPI app entry point
│   ├── config.py              # Paths, limits, tunables
│   ├── job_queue.py           # Background ThreadPoolExecutor job queue
│   ├── pipeline.py            # Orchestrates the full editing pipeline
│   ├── routes/
│   │   ├── upload.py           # POST /api/upload
│   │   ├── process.py          # GET  /api/status/{id}, /api/preview/{id}
│   │   ├── dashboard.py        # GET  /api/dashboard/stats, /jobs
│   │   └── download.py         # GET  /api/download/{id}
│   ├── ai/
│   │   ├── scene_detect.py     # PySceneDetect wrapper
│   │   ├── silence_remove.py   # ffmpeg silencedetect -> keep-segments
│   │   ├── face_detect.py      # MediaPipe face tracking
│   │   ├── auto_crop.py        # Face-centered crop/zoom filter builder
│   │   ├── color_enhance.py    # OpenCV brightness analysis + ffmpeg eq/denoise/sharpen
│   │   ├── stabilize.py        # ffmpeg vidstab two-pass stabilization
│   │   ├── audio_normalize.py  # Loudness measurement (volumedetect)
│   │   └── subtitles.py        # Local Whisper transcription -> SRT
│   ├── ffmpeg/ffmpeg_utils.py  # All ffmpeg/ffprobe command wrappers
│   ├── database/db.py          # SQLite persistence (jobs table)
│   ├── utils/{security,logger}.py
│   ├── uploads/                # Uploaded source videos (created at runtime)
│   └── outputs/                # Rendered 720p/1080p exports (created at runtime)
│
└── requirements.txt
```

## Prerequisites

1. **Python 3.10 or 3.11** (Whisper/torch wheels are most reliable on these versions).
2. **FFmpeg** compiled with `libx264`, `libvidstab` and `libass` (for subtitle burn-in).
   - Ubuntu/Debian: `sudo apt install ffmpeg` (most distro builds already include these).
   - macOS: `brew install ffmpeg`
   - Windows: install a "full" FFmpeg build (e.g. from gyan.dev) and add it to PATH.
3. At least **4GB of free RAM** (Whisper's `base` model + OpenCV + MediaPipe all load into memory).

Verify FFmpeg has what it needs:

```bash
ffmpeg -filters | grep vidstab
ffmpeg -filters | grep subtitles
```

If either is missing, stabilization falls back to a pass-through copy and
subtitle burn-in will fail for that job — install a fuller FFmpeg build to
enable both features.

## Setup

```bash
# 1. Clone / unzip the project, then from the project root:
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. (First run only) pre-download the Whisper model so the first upload
#    isn't slowed down by a model download:
python -c "import whisper; whisper.load_model('base')"
```

## Running the app

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in your browser. The FastAPI backend
serves the vanilla-JS frontend directly, so no separate frontend server is
required. If you prefer to serve the frontend separately (e.g. via `python
-m http.server` from `/frontend`), update `API_BASE` resolution in
`frontend/js/main.js` to point at the backend's URL, and make sure
`CORS_ORIGINS` in `backend/config.py` allows that origin.

## Using it

1. Go to **Edit a video**, drag in an MP4/MOV/AVI file (or click to browse).
2. Choose an output aspect ratio, whether to burn in subtitles, and
   optionally attach a background music track.
3. Click **Start AI editing** — the upload progress bar runs first, then
   the processing panel polls `/api/status/{job_id}` every second and
   lights up each pipeline stage as it completes.
4. When done, preview the result inline and download the 720p or 1080p
   export.
5. Visit **Dashboard** any time to see total videos, queue depth,
   completed/failed counts, storage usage and a live job history table.

## Configuration knobs (backend/config.py)

| Setting | Purpose |
|---|---|
| `MAX_UPLOAD_SIZE_BYTES` | Hard upload size cap (default 2GB) |
| `SILENCE_THRESHOLD_DB` / `SILENCE_MIN_DURATION` | How aggressively silence is trimmed |
| `SCENE_DETECT_THRESHOLD` | PySceneDetect sensitivity (lower = more cuts detected) |
| `WHISPER_MODEL_SIZE` | `tiny` is fastest/least accurate, `small`/`medium` are slower/more accurate |
| `MAX_WORKER_THREADS` | How many videos are transcoded concurrently |
| `EXPORT_PRESETS` | Bitrate/resolution for the 720p and 1080p renders |

## Notes on performance & scaling

- Jobs run on a fixed-size `ThreadPoolExecutor` (`MAX_WORKER_THREADS`), so
  uploads beyond that concurrency limit sit in the queue rather than
  fighting for CPU/GPU — increase the worker count only if your machine has
  the cores/RAM to back it.
- All heavy lifting is offloaded to FFmpeg's native (C/SIMD-optimized)
  filters wherever possible; OpenCV/MediaPipe only sample a handful of
  frames for face/brightness analysis rather than processing every frame,
  keeping memory flat regardless of video length.
- The SQLite connection uses WAL mode so the API can keep reading job
  status while a background thread writes progress updates.
- Every stage is wrapped in try/except at the top level of `pipeline.py`;
  a failure at any stage marks the job `failed` with the underlying error
  message instead of crashing the server process.

## Security notes

- Uploaded filenames are stripped of path components and given a random
  prefix before being written to disk (`utils/security.sanitize_filename`).
- Only `.mp4`, `.mov`, `.avi` extensions and matching MIME types are
  accepted; uploads are streamed to disk in 1MB chunks with a hard size
  cap enforced mid-stream (not just after the fact).
- A simple sliding-window rate limiter throttles the upload endpoint per
  client IP (`RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS`).
- Download/preview routes only ever serve paths recorded in the database
  against the requested `job_id` — there is no user-supplied filesystem
  path anywhere in the request surface.
