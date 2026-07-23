"""
security.py
Helpers that keep the upload endpoint safe: filename sanitization,
extension/mime validation and a lightweight in-memory rate limiter.
"""

import os
import re
import time
import uuid
from collections import defaultdict, deque

from config import ALLOWED_EXTENSIONS, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS

# Maps client IP -> deque of request timestamps, used for the rate limiter.
_request_log = defaultdict(deque)


def sanitize_filename(filename: str) -> str:
    """
    Strip directory components and dangerous characters from a filename,
    then prefix it with a random UUID so two uploads can never collide
    and a malicious name can never be used to traverse directories.
    """
    base_name = os.path.basename(filename)
    base_name = re.sub(r"[^A-Za-z0-9._-]", "_", base_name)
    unique_prefix = uuid.uuid4().hex[:12]
    return f"{unique_prefix}_{base_name}"


def is_allowed_extension(filename: str) -> bool:
    """Check the file extension against the whitelist (case-insensitive)."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def is_within_size_limit(size_bytes: int, max_bytes: int) -> bool:
    """Simple bound check used after the file has been streamed to disk."""
    return 0 < size_bytes <= max_bytes


def check_rate_limit(client_ip: str) -> bool:
    """
    Sliding-window rate limiter. Returns True if the request is allowed,
    False if the client has exceeded RATE_LIMIT_REQUESTS in the current
    RATE_LIMIT_WINDOW_SECONDS window.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    timestamps = _request_log[client_ip]

    # Drop timestamps that have fallen out of the window.
    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()

    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        return False

    timestamps.append(now)
    return True
