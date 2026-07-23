"""
routes/download.py
Serves finished output files as attachments. Only ever serves paths that
are recorded in the database against the requested job_id, so a client can
never traverse the filesystem via a crafted job_id or resolution value.
"""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from database import db

router = APIRouter()


@router.get("/api/download/{job_id}")
async def download_video(job_id: str, resolution: str = "1080p"):
    """Download the finished export at the requested resolution (720p/1080p)."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="Job has not finished processing yet")

    path = job["output_1080p"] if resolution == "1080p" else job["output_720p"]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Requested export is not available")

    download_name = f"{job['original_filename'].rsplit('.', 1)[0]}_{resolution}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=download_name)
