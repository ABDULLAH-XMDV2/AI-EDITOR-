"""
color_enhance.py
Analyzes average frame brightness with OpenCV and builds an ffmpeg filter
chain that auto-corrects exposure, boosts color saturation/contrast,
reduces noise and sharpens the image.
"""

import cv2
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


def analyze_brightness(video_path: str, sample_count: int = 15) -> float:
    """Sample frames and return the average luma (0-255) of the clip."""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return 128.0

    sample_indices = np.linspace(0, total_frames - 1, num=min(sample_count, total_frames), dtype=int)
    brightness_values = []
    for idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        success, frame = cap.read()
        if not success:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness_values.append(float(np.mean(gray)))

    cap.release()
    return float(np.mean(brightness_values)) if brightness_values else 128.0


def build_enhancement_filter(video_path: str) -> str:
    """
    Build a combined -vf filter string that:
    - corrects brightness/gamma if the clip is too dark or too bright
    - boosts saturation and contrast slightly for a punchier look
    - denoises with hqdn3d
    - sharpens with unsharp
    """
    avg_brightness = analyze_brightness(video_path)
    logger.info("Average brightness for %s: %.2f", video_path, avg_brightness)

    # Target a mid brightness of ~128; compute a gentle gamma correction.
    if avg_brightness < 90:
        gamma = 1.25   # brighten dark footage
        brightness_offset = 0.04
    elif avg_brightness > 180:
        gamma = 0.85   # tone down overexposed footage
        brightness_offset = -0.03
    else:
        gamma = 1.0
        brightness_offset = 0.0

    filters = [
        f"eq=brightness={brightness_offset}:contrast=1.08:saturation=1.15:gamma={gamma}",
        "hqdn3d=2:1.5:6:6",
        "unsharp=5:5:0.8:3:3:0.4",
    ]
    filter_str = ",".join(filters)
    logger.info("Built color enhancement filter: %s", filter_str)
    return filter_str
