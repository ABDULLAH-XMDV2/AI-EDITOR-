"""
routes/dashboard.py
Provides the aggregate statistics and job history used by dashboard.html:
total videos, queue length, completed/failed counts and storage usage.
"""

from fastapi import APIRouter

from database import db

router = APIRouter()


@router.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Return the summary cards data (totals, queue, completed, failed, storage)."""
    return db.dashboard_stats()


@router.get("/api/dashboard/jobs")
async def get_recent_jobs(limit: int = 50):
    """Return the most recent jobs with their status, sizes and timings for a table view."""
    jobs = db.list_jobs(limit=limit)
    return {
        "jobs": [
            {
                "job_id": job["id"],
                "original_filename": job["original_filename"],
                "status": job["status"],
                "progress": job["progress"],
                "current_step": job["current_step"],
                "input_size_bytes": job["input_size_bytes"],
                "output_size_bytes": job["output_size_bytes"],
                "created_at": job["created_at"],
                "error_message": job["error_message"],
            }
            for job in jobs
        ]
    }
