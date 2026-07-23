"""
subtitles.py
Generates an SRT subtitle file from a video's speech using OpenAI's local
Whisper model (no API calls, fully offline). The resulting .srt file is
later hard-burned into the final render by ffmpeg_utils.burn_subtitles.
"""

import os

import whisper

from config import WHISPER_MODEL_SIZE
from utils.logger import get_logger

logger = get_logger(__name__)

# Whisper models are fairly large to load; cache a single instance per
# process so repeated jobs don't reload weights from disk every time.
_model_cache = {}


def _get_model():
    """Lazily load (and cache) the configured Whisper model size."""
    if WHISPER_MODEL_SIZE not in _model_cache:
        logger.info("Loading Whisper model '%s' (first use, may take a moment)", WHISPER_MODEL_SIZE)
        _model_cache[WHISPER_MODEL_SIZE] = whisper.load_model(WHISPER_MODEL_SIZE)
    return _model_cache[WHISPER_MODEL_SIZE]


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to an SRT timestamp string: HH:MM:SS,mmm."""
    milliseconds = int(round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def generate_subtitles(audio_or_video_path: str, srt_output_path: str) -> str:
    """
    Transcribe speech in the given media file with Whisper and write an
    SRT file to srt_output_path. Returns the path to the written file.
    If no speech is detected, an empty (but valid) SRT file is written.
    """
    model = _get_model()
    logger.info("Transcribing %s with Whisper", audio_or_video_path)
    result = model.transcribe(audio_or_video_path, fp16=False, verbose=False)

    segments = result.get("segments", [])
    with open(srt_output_path, "w", encoding="utf-8") as srt_file:
        for i, segment in enumerate(segments, start=1):
            start_ts = _format_timestamp(segment["start"])
            end_ts = _format_timestamp(segment["end"])
            text = segment["text"].strip()
            srt_file.write(f"{i}\n{start_ts} --> {end_ts}\n{text}\n\n")

    logger.info("Wrote %d subtitle segments to %s", len(segments), srt_output_path)
    return srt_output_path
