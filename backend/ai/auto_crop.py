"""
auto_crop.py
Builds an ffmpeg crop/zoom/scale filter string that re-frames the video
around the detected face center, targeting a chosen output aspect ratio
(e.g. 9:16 for shorts, 1:1 for square, 16:9 to keep landscape).
"""

from config import TARGET_CROP_ASPECT
from utils.logger import get_logger

logger = get_logger(__name__)


def build_crop_filter(face_info: dict, target_aspect: tuple = TARGET_CROP_ASPECT, zoom: float = 1.08) -> str:
    """
    Given the output of face_detect.analyze_faces, compute a crop=w:h:x:y
    filter (optionally followed by a slight zoom) that keeps the detected
    face roughly centered while cropping to target_aspect.
    """
    frame_width = face_info.get("frame_width", 1920)
    frame_height = face_info.get("frame_height", 1080)
    aspect_w, aspect_h = target_aspect
    target_ratio = aspect_w / aspect_h
    source_ratio = frame_width / frame_height

    if target_ratio < source_ratio:
        # Target is narrower than source -> crop the width, keep full height.
        crop_height = frame_height
        crop_width = int(round(crop_height * target_ratio))
    else:
        # Target is wider/taller than source -> crop the height, keep full width.
        crop_width = frame_width
        crop_height = int(round(crop_width / target_ratio))

    # Clamp the crop box to the frame and center it on the face.
    center_x = face_info.get("center_x", 0.5) * frame_width
    center_y = face_info.get("center_y", 0.5) * frame_height

    crop_x = int(round(center_x - crop_width / 2))
    crop_y = int(round(center_y - crop_height / 2))
    crop_x = max(0, min(crop_x, frame_width - crop_width))
    crop_y = max(0, min(crop_y, frame_height - crop_height))

    zoom_factor = zoom if face_info.get("face_found") else 1.0

    filter_str = (
        f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
        f"scale=iw*{zoom_factor}:ih*{zoom_factor},"
        f"crop={crop_width}:{crop_height}"
    )
    logger.info("Built auto-crop filter: %s", filter_str)
    return filter_str
