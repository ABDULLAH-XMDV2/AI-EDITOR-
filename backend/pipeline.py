"""
pipeline.py
Orchestrates the full auto-editing pipeline for a single job:
scene detection -> silence removal -> face detection -> auto crop/zoom ->
color/sharpness/noise enhancement -> stabilization -> audio normalization ->
subtitle generation/burn-in -> optional background music -> smart
transitions -> final export at 720p and 1080p.

Each step updates the job's progress percentage and current_step label in
SQLite so the frontend can poll /api/status/{job_id} for live updates.
"""

import json
import os
import shutil
import tempfile
import time

from ai.audio_normalize import measure_volume
from ai.auto_crop import build_crop_filter
from ai.color_enhance import build_enhancement_filter
from ai.face_detect import analyze_faces
from ai.scene_detect import detect_scenes
from ai.silence_remove import get_keep_segments
from ai.stabilize import stabilize_video
from ai.subtitles import generate_subtitles
from config import EXPORT_PRESETS, OUTPUT_DIR
from database import db
from ffmpeg.ffmpeg_utils import (
    add_crossfade_transitions,
    apply_video_filters,
    burn_subtitles,
    cut_segments,
    export_resolution,
    extract_audio,
    mix_background_music,
    normalize_audio,
    probe_video,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# Step name -> progress percentage reached upon completion of that step.
_PROGRESS_MAP = {
    "validating": 2,
    "detecting_scenes": 8,
    "removing_silence": 20,
    "detecting_faces": 28,
    "auto_cropping": 38,
    "enhancing_color": 50,
    "stabilizing": 62,
    "normalizing_audio": 70,
    "generating_subtitles": 80,
    "burning_subtitles": 85,
    "adding_music": 88,
    "smart_transitions": 92,
    "exporting_720p": 96,
    "exporting_1080p": 100,
}


def _set_progress(job_id: str, step: str):
    """Persist the current step name and its associated progress percentage."""
    db.update_job(job_id, current_step=step, progress=_PROGRESS_MAP.get(step, 0))
    logger.info("Job %s -> %s (%d%%)", job_id, step, _PROGRESS_MAP.get(step, 0))


def run_pipeline(job_id: str, input_path: str, options: dict):
    """
    Execute the entire editing pipeline for one uploaded video.
    `options` is a dict such as:
        {
            "target_aspect": [9, 16],
            "add_subtitles": true,
            "background_music_path": null or "path/to/track.mp3",
            "music_volume": 0.15
        }
    Any raised exception marks the job as 'failed' with the error message
    stored on the row; success marks it 'completed' with both export paths.
    """
    work_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
    db.update_job(job_id, status="processing", started_at=time.time())

    try:
        # --- Step: validate --------------------------------------------------
        _set_progress(job_id, "validating")
        metadata = probe_video(input_path)
        current = os.path.join(work_dir, "00_source.mp4")
        shutil.copy(input_path, current)

        # --- Step: scene detection (informational, feeds transitions later) --
        _set_progress(job_id, "detecting_scenes")
        scene_cuts = detect_scenes(current)

        # --- Step: silence removal --------------------------------------------
        _set_progress(job_id, "removing_silence")
        keep_segments = get_keep_segments(current)
        no_silence_path = os.path.join(work_dir, "01_nosilence.mp4")
        cut_segments(current, keep_segments, no_silence_path)
        current = no_silence_path

        # --- Step: face detection ----------------------------------------------
        _set_progress(job_id, "detecting_faces")
        face_info = analyze_faces(current)

        # --- Step: auto crop / auto scale / auto zoom ---------------------------
        _set_progress(job_id, "auto_cropping")
        target_aspect = tuple(options.get("target_aspect", (9, 16)))
        crop_filter = build_crop_filter(face_info, target_aspect=target_aspect)
        cropped_path = os.path.join(work_dir, "02_cropped.mp4")
        apply_video_filters(current, cropped_path, crop_filter)
        current = cropped_path

        # --- Step: color / brightness / sharpness / noise enhancement -----------
        _set_progress(job_id, "enhancing_color")
        enhancement_filter = build_enhancement_filter(current)
        enhanced_path = os.path.join(work_dir, "03_enhanced.mp4")
        apply_video_filters(current, enhanced_path, enhancement_filter)
        current = enhanced_path

        # --- Step: stabilization ---------------------------------------------
        _set_progress(job_id, "stabilizing")
        stabilized_path = os.path.join(work_dir, "04_stabilized.mp4")
        stabilize_video(current, stabilized_path)
        current = stabilized_path

        # --- Step: audio normalization -----------------------------------------
        _set_progress(job_id, "normalizing_audio")
        if metadata["has_audio"]:
            before_stats = measure_volume(current)
            normalized_path = os.path.join(work_dir, "05_normalized.mp4")
            normalize_audio(current, normalized_path)
            current = normalized_path
            logger.info("Job %s loudness before normalization: %s", job_id, before_stats)

        # --- Step: subtitle generation -------------------------------------------
        srt_path = None
        if options.get("add_subtitles", True) and metadata["has_audio"]:
            _set_progress(job_id, "generating_subtitles")
            audio_wav = os.path.join(work_dir, "audio.wav")
            extract_audio(current, audio_wav)
            srt_path = os.path.join(work_dir, "subtitles.srt")
            generate_subtitles(audio_wav, srt_path)
            db.update_job(job_id, subtitle_path=srt_path)

            _set_progress(job_id, "burning_subtitles")
            subtitled_path = os.path.join(work_dir, "06_subtitled.mp4")
            burn_subtitles(current, srt_path, subtitled_path)
            current = subtitled_path
        else:
            _set_progress(job_id, "burning_subtitles")

        # --- Step: optional background music -------------------------------------
        music_path = options.get("background_music_path")
        if music_path and os.path.exists(music_path):
            _set_progress(job_id, "adding_music")
            music_volume = float(options.get("music_volume", 0.15))
            music_mixed_path = os.path.join(work_dir, "07_music.mp4")
            mix_background_music(current, music_path, music_mixed_path, music_volume)
            current = music_mixed_path
        else:
            _set_progress(job_id, "adding_music")

        # --- Step: smart transitions at detected scene cuts ------------------------
        _set_progress(job_id, "smart_transitions")
        transitions_path = os.path.join(work_dir, "08_transitions.mp4")
        add_crossfade_transitions(current, transitions_path, scene_cuts)
        current = transitions_path

        # --- Step: final export at 720p and 1080p ---------------------------------
        _set_progress(job_id, "exporting_720p")
        output_720p = os.path.join(OUTPUT_DIR, f"{job_id}_720p.mp4")
        preset_720 = EXPORT_PRESETS["720p"]
        export_resolution(current, output_720p, preset_720["width"], preset_720["height"], preset_720["bitrate"])

        _set_progress(job_id, "exporting_1080p")
        output_1080p = os.path.join(OUTPUT_DIR, f"{job_id}_1080p.mp4")
        preset_1080 = EXPORT_PRESETS["1080p"]
        export_resolution(current, output_1080p, preset_1080["width"], preset_1080["height"], preset_1080["bitrate"])

        output_size = os.path.getsize(output_1080p) + os.path.getsize(output_720p)

        db.update_job(
            job_id,
            status="completed",
            progress=100,
            current_step="completed",
            output_720p=output_720p,
            output_1080p=output_1080p,
            output_size_bytes=output_size,
            completed_at=time.time(),
        )
        logger.info("Job %s completed successfully", job_id)

    except Exception as exc:  # noqa: BLE001 - we want to catch and record ANY failure
        logger.exception("Job %s failed", job_id)
        db.update_job(
            job_id,
            status="failed",
            error_message=str(exc),
            completed_at=time.time(),
        )

    finally:
        # Always clean up the temporary working directory, success or failure.
        shutil.rmtree(work_dir, ignore_errors=True)
