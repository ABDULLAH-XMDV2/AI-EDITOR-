"""
db.py
Thin SQLite persistence layer. Uses the standard library sqlite3 module with
a per-thread connection pattern (check_same_thread=False + a lock) since the
job queue runs processing in background threads.
"""

import sqlite3
import threading
import time
import uuid

from config import DATABASE_PATH

_lock = threading.Lock()


def get_connection():
    """Create a new SQLite connection with sane defaults (row factory, FKs)."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Create the jobs table if it does not already exist. Called on startup."""
    with _lock:
        conn = get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                current_step TEXT DEFAULT '',
                error_message TEXT DEFAULT '',
                options_json TEXT DEFAULT '{}',
                output_720p TEXT DEFAULT '',
                output_1080p TEXT DEFAULT '',
                subtitle_path TEXT DEFAULT '',
                input_size_bytes INTEGER DEFAULT 0,
                output_size_bytes INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL
            )
            """
        )
        conn.commit()
        conn.close()


def create_job(original_filename: str, stored_filename: str, size_bytes: int, options_json: str) -> str:
    """Insert a new job row in 'queued' state and return its generated id."""
    job_id = str(uuid.uuid4())
    with _lock:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO jobs (id, original_filename, stored_filename, status,
                               input_size_bytes, options_json, created_at)
            VALUES (?, ?, ?, 'queued', ?, ?, ?)
            """,
            (job_id, original_filename, stored_filename, size_bytes, options_json, time.time()),
        )
        conn.commit()
        conn.close()
    return job_id


def update_job(job_id: str, **fields):
    """Generic partial update of a job row. Pass column=value kwargs."""
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]
    with _lock:
        conn = get_connection()
        conn.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)
        conn.commit()
        conn.close()


def get_job(job_id: str):
    """Fetch a single job by id as a dict, or None if it doesn't exist."""
    with _lock:
        conn = get_connection()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
    return dict(row) if row else None


def list_jobs(limit: int = 100):
    """Return the most recent jobs, newest first."""
    with _lock:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def dashboard_stats():
    """Aggregate counts used by the dashboard cards."""
    with _lock:
        conn = get_connection()
        total = conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
        queued = conn.execute(
            "SELECT COUNT(*) c FROM jobs WHERE status IN ('queued','processing')"
        ).fetchone()["c"]
        completed = conn.execute(
            "SELECT COUNT(*) c FROM jobs WHERE status = 'completed'"
        ).fetchone()["c"]
        failed = conn.execute(
            "SELECT COUNT(*) c FROM jobs WHERE status = 'failed'"
        ).fetchone()["c"]
        storage = conn.execute(
            "SELECT COALESCE(SUM(input_size_bytes + output_size_bytes), 0) s FROM jobs"
        ).fetchone()["s"]
        conn.close()
    return {
        "total_videos": total,
        "processing_queue": queued,
        "completed_edits": completed,
        "failed_jobs": failed,
        "storage_usage_bytes": storage,
      }
  
