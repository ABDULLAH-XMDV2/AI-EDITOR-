"""
job_queue.py
A minimal background job queue built on Python's ThreadPoolExecutor.
FastAPI's request handlers simply call `enqueue_job(...)` and return
immediately; the actual heavy FFmpeg/AI work happens on worker threads so
uploads never block on processing.
"""

from concurrent.futures import ThreadPoolExecutor

from config import MAX_WORKER_THREADS
from pipeline import run_pipeline
from utils.logger import get_logger

logger = get_logger(__name__)

# A small fixed-size pool keeps memory/CPU usage predictable: only
# MAX_WORKER_THREADS videos are ever transcoded concurrently, the rest sit
# in the executor's internal queue with status 'queued' in the database.
_executor = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS, thread_name_prefix="video-job")


def enqueue_job(job_id: str, input_path: str, options: dict):
    """Submit a job to run in the background thread pool and return immediately."""
    logger.info("Enqueuing job %s", job_id)
    _executor.submit(_safe_run, job_id, input_path, options)


def _safe_run(job_id: str, input_path: str, options: dict):
    """Wrapper that guarantees an unexpected exception never kills a worker thread."""
    try:
        run_pipeline(job_id, input_path, options)
    except Exception:  # noqa: BLE001 - last line of defense, pipeline already logs details
        logger.exception("Unhandled exception while running job %s", job_id)


def shutdown_queue():
    """Gracefully wait for in-flight jobs to finish on application shutdown."""
    logger.info("Shutting down job queue, waiting for in-flight jobs...")
    _executor.shutdown(wait=True)
