"""
Master FFmpeg Assembly & Subtitle Burn-in Composer
Assembles normalized scene clips, synchronizes master narration audio, and burns stylized subtitles.
"""
import os
import subprocess
from typing import List

def create_concat_manifest(clips: List[str], manifest_path: str) -> None:
    """Generate concat demuxer manifest in strict UTF-8 without BOM with LF newlines."""
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        for clip in clips:
            safe_clip = os.path.abspath(clip).replace("\\", "/")
            f.write(f"file '{safe_clip}'\n")

def escape_windows_path_for_ffmpeg(path_str: str) -> str:
    """Escape Windows drive letter and path for FFmpeg filtergraph."""
    clean_path = os.path.abspath(path_str).replace("\\", "/")
    # Escape colon after drive letter: C:/ -> C\:/
    if len(clean_path) >= 2 and clean_path[1] == ":":
        clean_path = clean_path[0] + "\\:" + clean_path[2:]
    return clean_path

def assemble_master_documentary(
    clips: List[str],
    audio_path: str,
    srt_path: str,
    output_path: str,
    ffmpeg_path: str,
    manifest_path: str
) -> bool:
    """
    Concatenate video clips, bind narration audio, optionally burn stylized subtitles,
    and render the master documentary MP4.
    If srt_path is None or doesn't exist, skips subtitle burning.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 1. Generate concat manifest
    create_concat_manifest(clips, manifest_path)
    
    # 2. Build filter chain: subtitles (optional) + format
    if srt_path and os.path.exists(srt_path):
        escaped_srt = escape_windows_path_for_ffmpeg(srt_path)
        subtitle_filter = (
            f"subtitles='{escaped_srt}':"
            f"force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35',"
            f"format=yuv420p"
        )
    else:
        subtitle_filter = "format=yuv420p"
    
    # 3. Assemble FFmpeg command
    cmd = [
        ffmpeg_path, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", manifest_path,
        "-i", audio_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    
    print("\n--- MASTER RENDERING IN PROGRESS ---")
    print(f"  Target: {output_path}")
    print(f"  Encoding preset: fast | CRF: 20 | Audio: AAC 192k\n")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace"
    )
    
    # Monitor and stream progress lines
    for line in iter(process.stdout.readline, ""):
        line_s = line.strip()
        if "frame=" in line_s or "time=" in line_s or "fps=" in line_s:
            print(f"  [Render Progress] {line_s}", end="\r")
        elif "Error" in line_s or "fatal" in line_s:
            print(f"\n  [FFmpeg Warning/Error] {line_s}")
            
    process.stdout.close()
    returncode = process.wait()
    print("\n")
    
    if returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000000:
        return True
    return False
