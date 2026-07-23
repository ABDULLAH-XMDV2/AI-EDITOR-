"""
audio_normalize.py
Measures mean/max volume with ffmpeg's volumedetect filter so the pipeline
can log before/after loudness, then delegates the actual normalization to
ffmpeg_utils.normalize_audio (EBU R128 loudnorm + light denoise).
"""

import re
import subprocess

from utils.logger import get_logger

logger = get_logger(__name__)

_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB")
_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(-?\d+\.?\d*)\s*dB")


def measure_volume(video_path: str) -> dict:
    """Return {'mean_db': float, 'max_db': float} loudness stats for a clip."""
    cmd = ["ffmpeg", "-i", video_path, "-af", "volumedetect", "-f", "null", "-"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr = result.stderr

    mean_match = _MEAN_VOLUME_RE.search(stderr)
    max_match = _MAX_VOLUME_RE.search(stderr)

    stats = {
        "mean_db": float(mean_match.group(1)) if mean_match else None,
        "max_db": float(max_match.group(1)) if max_match else None,
    }
    logger.info("Volume stats for %s: %s", video_path, stats)
    return stats
