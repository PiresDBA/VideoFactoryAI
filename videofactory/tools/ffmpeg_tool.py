"""
Robust FFmpeg Tooling for VideoFactoryAI.
Handles duration extraction, Ken Burns motion filtering, video normalization,
manifest generation, subtitle burn-in, and master video encoding.
"""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

def escape_windows_path_for_ffmpeg(path_str: str) -> str:
    """Escape Windows drive letter and path for FFmpeg filtergraph (C\\:/...)."""
    clean_path = str(Path(path_str).resolve()).replace("\\", "/")
    if len(clean_path) >= 2 and clean_path[1] == ":":
        clean_path = clean_path[0] + "\\:" + clean_path[2:]
    return clean_path

def get_media_duration(media_path: str, ffmpeg_path: str) -> float:
    """Extract audio or video duration in seconds using ffmpeg."""
    if not os.path.exists(media_path):
        return 0.0
    cmd = [ffmpeg_path, "-i", media_path]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors="replace")
    m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res.stderr)
    if m:
        h, mn, s = m.groups()
        return round(int(h) * 3600 + int(mn) * 60 + float(s), 3)
    return 0.0

def get_video_specs(media_path: str, ffmpeg_path: str) -> Dict[str, Any]:
    """Retrieve video resolution, fps, and codecs."""
    specs = {"width": 0, "height": 0, "fps": 0.0, "has_video": False, "has_audio": False}
    if not os.path.exists(media_path):
        return specs
        
    cmd = [ffmpeg_path, "-i", media_path]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, errors="replace")
    
    # Check resolution
    res_m = re.search(r"Video:.*?,.*?,\s*(\d{3,5})x(\d{3,5})", res.stderr)
    if res_m:
        specs["width"] = int(res_m.group(1))
        specs["height"] = int(res_m.group(2))
        specs["has_video"] = True
        
    # Check FPS
    fps_m = re.search(r"(\d+(?:\.\d+)?)\s*fps", res.stderr)
    if fps_m:
        specs["fps"] = float(fps_m.group(1))
        
    if "Audio:" in res.stderr:
        specs["has_audio"] = True
        
    return specs

def create_concat_manifest(clips: List[str], manifest_path: str) -> None:
    """Create concat demuxer manifest in strict UTF-8 without BOM with LF newlines."""
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        for clip in clips:
            safe_clip = str(Path(clip).resolve()).replace("\\", "/")
            f.write(f"file '{safe_clip}'\n")

def render_ken_burns_clip(
    image_path: str,
    output_clip_path: str,
    duration: float,
    ffmpeg_path: str,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    zoom_speed: float = 0.0008,
    scene_index: int = 1
) -> bool:
    """Generate a cinematic Ken Burns zoompan clip from a static image."""
    frames = max(1, int(round(duration * fps)))
    
    # Cinematic Ken Burns with 4K pre-scaling and smooth sinusoidal ease
    # Pre-scaling to 4K (3840x2160) eliminates 1-pixel quantization vibration.
    # The sinusoidal zoom '1.02 + 0.10*sin(PI*on/frames)' smoothly pushes in and gently pulls out.
    z_expr = f"'1.02+0.10*sin(PI*on/{frames})'"
    x_expr = "'iw/2-(iw/zoom/2)'"
    y_expr = "'ih/2-(ih/zoom/2)'"

    vf_filter = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"zoompan=z={z_expr}:d={frames}:x={x_expr}:y={y_expr}:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )

    cmd = [
        ffmpeg_path, "-y",
        "-loop", "1",
        "-i", str(Path(image_path).resolve()),
        "-vf", vf_filter,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        str(Path(output_clip_path).resolve())
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"    [FFmpeg KenBurns Error] {res.stderr[-300:]}")
        return False
    return os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000

def normalize_video_clip(
    video_path: str,
    output_clip_path: str,
    duration: float,
    ffmpeg_path: str,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30
) -> bool:
    """Normalize video: loop if short, scale & pad to target, strip audio, fix framerate."""
    vf_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},format=yuv420p"
    )
    cmd = [
        ffmpeg_path, "-y",
        "-stream_loop", "-1",
        "-i", str(Path(video_path).resolve()),
        "-t", f"{duration:.3f}",
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        str(Path(output_clip_path).resolve())
    ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"    [FFmpeg Normalize Video Error] {res.stderr[-300:]}")
        return False
    return os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000

def assemble_master_video(
    manifest_path: str,
    audio_path: str,
    srt_path: str,
    output_path: str,
    ffmpeg_path: str,
    font_size: int = 24,
    margin_v: int = 35,
    crf: int = 20,
    preset: str = "fast"
) -> bool:
    """Concatenate video clips, attach narration audio, burn subtitles and render."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    escaped_srt = escape_windows_path_for_ffmpeg(srt_path)

    subtitle_filter = (
        f"subtitles='{escaped_srt}':"
        f"force_style='FontSize={font_size},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV={margin_v}'"
    )

    cmd = [
        ffmpeg_path, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(Path(manifest_path).resolve()),
        "-i", str(Path(audio_path).resolve()),
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(Path(output_path).resolve())
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace"
    )

    for line in iter(process.stdout.readline, ""):
        line_s = line.strip()
        if "frame=" in line_s or "time=" in line_s or "fps=" in line_s:
            print(f"  [FFmpeg Render] {line_s}", end="\r")
        elif "Error" in line_s or "fatal" in line_s:
            print(f"\n  [FFmpeg Log] {line_s}")

    process.stdout.close()
    returncode = process.wait()
    print()

    return returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 500000
