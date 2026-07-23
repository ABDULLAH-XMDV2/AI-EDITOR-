"""
config.py
Central configuration for the AI Auto Video Editor backend.
All paths, limits and tunables live here so the rest of the codebase
never hard-codes a magic number or path.
"""

import os

# ---------------------------------------------------------------------------
# Base directories
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "app.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Make sure every required directory exists at import time.
for _dir in (UPLOAD_DIR, OUTPUT_DIR, DATABASE_DIR, LOG_DIR):
    os.makedirs(_dir, exist_ok=True)

# ---------------------------------------------------------------------------
# Upload / security limits
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi"}
ALLOWED_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/avi",
}
MAX_UPLOAD_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB hard limit per file
CHUNK_SIZE = 1024 * 1024  # 1 MB streamed read/write chunks

# Simple in-memory rate limiting: N requests per window per IP.
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60

# ---------------------------------------------------------------------------
# Processing / AI tunables
# ---------------------------------------------------------------------------
SILENCE_THRESHOLD_DB = -35        # dBFS below which audio is considered silent
SILENCE_MIN_DURATION = 0.6        # seconds of continuous silence required to cut
SCENE_DETECT_THRESHOLD = 27.0     # PySceneDetect ContentDetector sensitivity
WHISPER_MODEL_SIZE = "base"       # tiny | base | small | medium | large
TARGET_CROP_ASPECT = (9, 16)      # default auto-crop aspect ratio (portrait)
MAX_WORKER_THREADS = 2            # concurrent video jobs processed at once

EXPORT_PRESETS = {
    "720p": {"width": 1280, "height": 720, "bitrate": "3500k"},
    "1080p": {"width": 1920, "height": 1080, "bitrate": "6000k"},
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ORIGINS = ["*"]  # tightened by reverse proxy in production
