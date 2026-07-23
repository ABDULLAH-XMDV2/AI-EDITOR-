"""
main.py
FastAPI application entry point. Wires up CORS, mounts the frontend as
static files, registers the API routers and initializes the SQLite
database on startup. Run with:

    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS
from database.db import init_db
from job_queue import shutdown_queue
from routes import dashboard, download, process, upload
from utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="AI Auto Video Editor",
    description="Local, open-source AI video auto-editing backend",
    version="1.0.0",
)

# --- CORS: allow the frontend (served separately or from the same origin) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API routers -------------------------------------------------------------
app.include_router(upload.router, tags=["upload"])
app.include_router(process.router, tags=["processing"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(download.router, tags=["download"])


@app.on_event("startup")
async def on_startup():
    """Initialize the SQLite schema when the server boots."""
    logger.info("Starting AI Auto Video Editor backend...")
    init_db()
    logger.info("Database ready.")


@app.on_event("shutdown")
async def on_shutdown():
    """Let in-flight background jobs finish before the process exits."""
    shutdown_queue()


@app.get("/api/health")
async def health_check():
    """Basic liveness probe used by monitoring / the setup script."""
    return {"status": "ok"}


# --- Serve the vanilla JS frontend from the same FastAPI process ------------
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
