"""
routes/process.py
Exposes job status polling so the frontend can show a live progress bar.
Also exposes a preview endpoint for the finished 720p file so the browser
can play it back inline before the user downloads.
"""

import os
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from database import db

router = APIRouter()


@router.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Return the current progress/status for a job, plus timing/size info."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    processing_time = None
    if job["started_at"]:
        end_time = job["completed_at"] or time.time()
        processing_time = round(end_time - job["started_at"], 1)

    return {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "current_step": job["current_step"],
        "error_message": job["error_message"],
        "processing_time_seconds": processing_time,
        "input_size_bytes": job["input_size_bytes"],
        "output_size_bytes": job["output_size_bytes"],
        "has_720p": bool(job["output_720p"]),
        "has_1080p": bool(job["output_1080p"]),
    }


@router.get("/api/preview/{job_id}")
async def preview_video(job_id: str, resolution: str = "720p"):
    """Stream the finished video back for inline <video> preview playback."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    path = job["output_1080p"] if resolution == "1080p" else job["output_720p"]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output not ready yet")

    return FileResponse(path, media_type="video/mp4")
