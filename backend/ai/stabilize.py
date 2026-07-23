"""
stabilize.py
Two-pass video stabilization using ffmpeg's libvidstab filters
(vidstabdetect + vidstabtransform). Pass 1 analyzes camera shake and writes
a transform log; pass 2 applies the smoothed transform to the footage.
"""

import os
import tempfile

from ffmpeg.ffmpeg_utils import run_command
from utils.logger import get_logger

logger = get_logger(__name__)


def stabilize_video(input_path: str, output_path: str, shakiness: int = 5, smoothing: int = 15):
    """
    Run the two-pass vidstab pipeline. Falls back to a plain copy if
    libvidstab is unavailable in the installed ffmpeg build, so a missing
    optional codec never crashes the whole job.
    """
    transform_log = tempfile.NamedTemporaryFile(suffix=".trf", delete=False).name

    try:
        # Pass 1: detect motion vectors and write them to the transform log.
        detect_cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", f"vidstabdetect=shakiness={shakiness}:accuracy=15:result={transform_log}",
            "-f", "null", "-",
        ]
        run_command(detect_cmd)

        # Pass 2: apply the smoothed transform to produce a stabilized output.
        transform_cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", f"vidstabtransform=input={transform_log}:smoothing={smoothing}:zoom=0:optzoom=1,"
                   f"unsharp=5:5:0.8:3:3:0.4",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "copy", output_path,
        ]
        run_command(transform_cmd)
        logger.info("Stabilization complete: %s", output_path)

    except RuntimeError as exc:
        logger.warning("Stabilization unavailable (%s), copying input through unchanged", exc)
        run_command(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path])

    finally:
        if os.path.exists(transform_log):
            os.remove(transform_log)
          
