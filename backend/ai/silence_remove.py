"""
silence_remove.py
Detects silent stretches of audio using ffmpeg's silencedetect filter and
converts them into the list of "keep" segments that ffmpeg_utils.cut_segments
uses to produce a silence-free cut of the video.
"""

import re
import subprocess

from config import SILENCE_THRESHOLD_DB, SILENCE_MIN_DURATION
from ffmpeg.ffmpeg_utils import probe_video
from utils.logger import get_logger

logger = get_logger(__name__)

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?\d+\.?\d*)")


def _detect_silence_ranges(video_path: str) -> list:
    """Run ffmpeg silencedetect and parse the (start, end) silence ranges from stderr."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={SILENCE_MIN_DURATION}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = result.stderr.splitlines()

    ranges = []
    current_start = None
    for line in lines:
        start_match = _SILENCE_START_RE.search(line)
        end_match = _SILENCE_END_RE.search(line)
        if start_match:
            current_start = float(start_match.group(1))
        elif end_match and current_start is not None:
            ranges.append((current_start, float(end_match.group(1))))
            current_start = None

    return ranges


def get_keep_segments(video_path: str) -> list:
    """
    Compute the segments of the video that should be KEPT (i.e. everything
    that is not silence), as a list of (start, end) tuples in seconds.
    If the source has no audio track or no silence is found, the whole
    video is returned as a single keep-segment.
    """
    metadata = probe_video(video_path)
    duration = metadata["duration"]

    if not metadata["has_audio"]:
        logger.info("No audio track detected, skipping silence removal")
        return [(0.0, duration)]

    silence_ranges = _detect_silence_ranges(video_path)
    if not silence_ranges:
        logger.info("No silent segments found in %s", video_path)
        return [(0.0, duration)]

    keep_segments = []
    cursor = 0.0
    for silence_start, silence_end in silence_ranges:
        if silence_start > cursor:
            keep_segments.append((cursor, silence_start))
        cursor = max(cursor, silence_end)

    if cursor < duration:
        keep_segments.append((cursor, duration))

    # Guard against pathological cases where everything was "silent".
    if not keep_segments:
        keep_segments = [(0.0, duration)]

    logger.info("Computed %d keep-segments after silence removal", len(keep_segments))
    return keep_segments
