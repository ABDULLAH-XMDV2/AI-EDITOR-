"""
scene_detect.py
Wraps PySceneDetect's ContentDetector to find hard scene cuts in the source
video. The resulting cut timestamps are used both for logging/UI purposes
and to drive the smart-transition step later in the pipeline.
"""

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

from config import SCENE_DETECT_THRESHOLD
from utils.logger import get_logger

logger = get_logger(__name__)


def detect_scenes(video_path: str) -> list:
    """
    Run content-aware scene detection on the given video file.
    Returns a list of scene-boundary timestamps in seconds (floats),
    excluding time 0.0 (the start of the video is not a "cut").
    """
    logger.info("Detecting scenes for %s", video_path)
    video = open_video(video_path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=SCENE_DETECT_THRESHOLD))

    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    # Each scene is a (start_timecode, end_timecode) pair; we only need the
    # start of every scene after the first as a "cut" timestamp.
    cuts = [scene[0].get_seconds() for scene in scene_list[1:]]

    logger.info("Detected %d scene cuts in %s", len(cuts), video_path)
    return cuts
