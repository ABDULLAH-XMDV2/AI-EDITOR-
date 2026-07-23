"""
face_detect.py
Uses MediaPipe Face Detection to sample frames throughout the video and
compute the average bounding box of the primary (largest) face. This box is
what auto_crop.py uses to decide where to center the crop/zoom.
"""

import cv2
import mediapipe as mp
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

_mp_face_detection = mp.solutions.face_detection


def analyze_faces(video_path: str, sample_count: int = 20) -> dict:
    """
    Sample up to `sample_count` evenly spaced frames from the video and run
    MediaPipe face detection on each. Returns a dict describing whether a
    face was found and its average relative center (cx, cy) in [0, 1]
    coordinates, plus the average relative face size.
    """
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if total_frames <= 0:
        cap.release()
        return {"face_found": False, "center_x": 0.5, "center_y": 0.5, "avg_size": 0.0}

    sample_indices = np.linspace(0, total_frames - 1, num=min(sample_count, total_frames), dtype=int)

    centers_x, centers_y, sizes = [], [], []

    with _mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as detector:
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            success, frame = cap.read()
            if not success:
                continue

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = detector.process(rgb_frame)
            if not result.detections:
                continue

            # Pick the largest detected face (closest to camera / most relevant).
            largest = max(
                result.detections,
                key=lambda d: d.location_data.relative_bounding_box.width
                * d.location_data.relative_bounding_box.height,
            )
            box = largest.location_data.relative_bounding_box
            centers_x.append(box.xmin + box.width / 2)
            centers_y.append(box.ymin + box.height / 2)
            sizes.append(max(box.width, box.height))

    cap.release()

    if not centers_x:
        logger.info("No faces detected in %s, defaulting to center crop", video_path)
        return {
            "face_found": False,
            "center_x": 0.5,
            "center_y": 0.5,
            "avg_size": 0.0,
            "frame_width": frame_width,
            "frame_height": frame_height,
        }

    result = {
        "face_found": True,
        "center_x": float(np.mean(centers_x)),
        "center_y": float(np.mean(centers_y)),
        "avg_size": float(np.mean(sizes)),
        "frame_width": frame_width,
        "frame_height": frame_height,
    }
    logger.info("Face analysis for %s: %s", video_path, result)
    return result
