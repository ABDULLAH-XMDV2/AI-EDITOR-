"""
routes/upload.py
Handles video uploads. Validates extension/mime/size, streams the file to
disk in chunks (so large uploads never load fully into memory), creates a
job row in SQLite and enqueues it on the background job queue.
"""

import json
import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from config import ALLOWED_MIME_TYPES, CHUNK_SIZE, MAX_UPLOAD_SIZE_BYTES, UPLOAD_DIR
from database import db
from job_queue import enqueue_job
from utils.logger import get_logger
from utils.security import (
    check_rate_limit,
    is_allowed_extension,
    is_within_size_limit,
    sanitize_filename,
)

router = APIRouter()
logger = get_logger(__name__)


@router.post("/api/upload")
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    target_aspect: str = Form("9:16"),
    add_subtitles: bool = Form(True),
    music_volume: float = Form(0.15),
    background_music: UploadFile = File(None),
):
    """
    Accept a multipart video upload plus a few AI-editing options, persist
    the file, create a job record and hand it off to the background queue.
    Returns the new job_id immediately so the frontend can start polling
    /api/status/{job_id} for progress.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down and try again shortly.")

    # --- Validate extension up front (cheap check before we touch the disk) ---
    if not is_allowed_extension(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload MP4, MOV or AVI.")

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {file.content_type}")

    # --- Stream to disk in chunks, enforcing the size limit as we go -----------
    safe_name = sanitize_filename(file.filename)
    saved_path = os.path.join(UPLOAD_DIR, safe_name)
    total_bytes = 0

    try:
        with open(saved_path, "wb") as out_file:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                    out_file.close()
                    os.remove(saved_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB upload limit.",
                    )
                out_file.write(chunk)
    finally:
        await file.close()

    if not is_within_size_limit(total_bytes, MAX_UPLOAD_SIZE_BYTES):
        os.remove(saved_path)
        raise HTTPException(status_code=400, detail="Uploaded file is empty or invalid.")

    # --- Optional background music upload --------------------------------------
    music_path = None
    if background_music is not None and background_music.filename:
        music_name = sanitize_filename(background_music.filename)
        music_path = os.path.join(UPLOAD_DIR, music_name)
        with open(music_path, "wb") as music_file:
            while True:
                chunk = await background_music.read(CHUNK_SIZE)
                if not chunk:
                    break
                music_file.write(chunk)
        await background_music.close()

    # --- Parse the target aspect ratio string ("9:16" -> (9, 16)) --------------
    try:
        aspect_parts = [int(p) for p in target_aspect.split(":")]
        if len(aspect_parts) != 2:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="target_aspect must look like '9:16'")

    options = {
        "target_aspect": aspect_parts,
        "add_subtitles": add_subtitles,
        "background_music_path": music_path,
        "music_volume": music_volume,
    }

    job_id = db.create_job(
        original_filename=file.filename,
        stored_filename=safe_name,
        size_bytes=total_bytes,
        options_json=json.dumps(options),
    )

    logger.info("Created job %s for file %s (%d bytes)", job_id, file.filename, total_bytes)
    enqueue_job(job_id, saved_path, options)

    return JSONResponse({"job_id": job_id, "status": "queued", "message": "Upload received, processing started."})
