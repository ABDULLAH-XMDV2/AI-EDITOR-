"""
ffmpeg_utils.py
Thin wrapper around the ffmpeg / ffprobe command line tools. Every function
shells out via subprocess, checks the return code and raises a descriptive
RuntimeError on failure so the pipeline can mark the job as failed with a
useful message instead of crashing silently.
"""

import json
import subprocess

from utils.logger import get_logger

logger = get_logger(__name__)


def run_command(cmd: list) -> str:
    """Run a shell command, return stdout, raise RuntimeError with stderr on failure."""
    logger.info("Running command: %s", " ".join(cmd))
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): {result.stderr[-2000:]}")
    return result.stdout


def probe_video(path: str) -> dict:
    """Return ffprobe metadata (duration, width, height, fps, has_audio) for a file."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    output = run_command(cmd)
    data = json.loads(output)

    video_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)

    if video_stream is None:
        raise RuntimeError("No video stream found in uploaded file")

    num, den = video_stream.get("avg_frame_rate", "25/1").split("/")
    fps = float(num) / float(den) if float(den) != 0 else 25.0

    return {
        "duration": float(data["format"].get("duration", 0)),
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "fps": round(fps, 2),
        "has_audio": audio_stream is not None,
        "size_bytes": int(data["format"].get("size", 0)),
    }


def extract_audio(input_path: str, output_wav_path: str):
    """Extract a mono 16kHz WAV track, the format Whisper/silence-detection expect."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", output_wav_path,
    ]
    run_command(cmd)


def cut_segments(input_path: str, segments: list, output_path: str):
    """
    Concatenate a list of (start, end) keep-segments from input_path into
    output_path using the ffmpeg concat demuxer, dropping everything else
    (used to remove detected silence).
    """
    if not segments:
        # Nothing to cut, just copy through.
        run_command(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path])
        return

    filter_parts = []
    concat_inputs = ""
    for i, (start, end) in enumerate(segments):
        filter_parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
        )
        concat_inputs += f"[v{i}][a{i}]"

    filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={len(segments)}:v=1:a=1[outv][outa]"

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", output_path,
    ]
    run_command(cmd)


def apply_video_filters(input_path: str, output_path: str, filter_chain: str, extra_args: list = None):
    """Apply an arbitrary -vf filter chain (crop/scale/eq/zoom/stabilize/etc)."""
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", filter_chain,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "copy"]
    if extra_args:
        cmd += extra_args
    cmd.append(output_path)
    run_command(cmd)


def normalize_audio(input_path: str, output_path: str):
    """Apply the loudnorm two-pass-equivalent single pass filter for consistent loudness."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,afftdn=nf=-25",
        "-c:v", "copy", output_path,
    ]
    run_command(cmd)


def mix_background_music(video_path: str, music_path: str, output_path: str, music_volume: float = 0.15):
    """Duck the original audio slightly and mix in a looped background music track."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-stream_loop", "-1", "-i", music_path,
        "-filter_complex",
        f"[0:a]volume=1.0[a0];[1:a]volume={music_volume}[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-shortest", output_path,
    ]
    run_command(cmd)


def burn_subtitles(input_path: str, srt_path: str, output_path: str):
    """Hard-burn an SRT subtitle file into the video track."""
    escaped_srt = srt_path.replace(":", "\\:").replace("'", "\\'")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"subtitles='{escaped_srt}':force_style='FontName=Arial,FontSize=20,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=1'",
        "-c:a", "copy", output_path,
    ]
    run_command(cmd)


def add_crossfade_transitions(input_path: str, output_path: str, scene_cuts: list, fade_duration: float = 0.4):
    """
    Apply short fade-in/fade-out transitions at every detected scene boundary
    so cuts feel like smart transitions instead of hard jump-cuts.
    """
    if not scene_cuts:
        run_command(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path])
        return

    fade_filters = []
    for cut_time in scene_cuts:
        start = max(cut_time - fade_duration / 2, 0)
        fade_filters.append(f"fade=t=in:st={start}:d={fade_duration}:alpha=0")

    filter_chain = ",".join(fade_filters) if fade_filters else "null"
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", filter_chain,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", output_path]
    run_command(cmd)


def export_resolution(input_path: str, output_path: str, width: int, height: int, bitrate: str):
    """Final render pass: scale to a target resolution/bitrate for delivery."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "medium", "-b:v", bitrate,
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        output_path,
    ]
    run_command(cmd)
  
