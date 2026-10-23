"""
Advanced Visual Processing & Motion Engineering
Standardizes all video clips and generates cinematic Ken Burns zoompan effects on static images.
"""
import os
import subprocess
from typing import List, Dict, Any

def process_single_scene(
    scene: Dict[str, Any],
    source_asset: str,
    output_clip_path: str,
    ffmpeg_path: str
) -> bool:
    """Normalize a single image or video asset to 1920x1080@30fps yuv420p matching scene duration."""
    scene_id = scene["id"]
    duration = scene["duration"]
    is_image = (scene["tipo"] == "image")
    frames = max(1, int(round(duration * 30)))
    
    if is_image:
        # Professional Ken Burns Zoompan
        # Alternating motion: even scenes zoom-in, odd scenes zoom-in with subtle pan
        zoom_speed = 0.0008
        vf_filter = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"zoompan=z='min(zoom+{zoom_speed},1.25)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s=1920x1080:fps=30,format=yuv420p"
        )
        cmd = [
            ffmpeg_path, "-y",
            "-loop", "1",
            "-i", source_asset,
            "-vf", vf_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",
            output_clip_path
        ]
    else:
        # Video Normalization: loop if shorter than duration, scale & pad, strip audio
        vf_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
            "fps=30,format=yuv420p"
        )
        cmd = [
            ffmpeg_path, "-y",
            "-stream_loop", "-1",
            "-i", source_asset,
            "-t", str(duration),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",
            output_clip_path
        ]

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"    [FFmpeg Error] Scene {scene_id}: {res.stderr[-300:]}")
        return False
        
    return os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000

def process_all_scenes(
    scenes: List[Dict[str, Any]],
    asset_map: Dict[int, str],
    temp_clips_dir: str,
    ffmpeg_path: str
) -> List[str]:
    """Process and normalize all scenes sequentially into standardized clips."""
    os.makedirs(temp_clips_dir, exist_ok=True)
    processed_clips = []
    
    total = len(scenes)
    for idx, s in enumerate(scenes, 1):
        scene_id = s["id"]
        source_asset = asset_map[scene_id]
        out_filename = f"clip_{scene_id:02d}.mp4"
        out_path = os.path.join(temp_clips_dir, out_filename)
        
        # Check if already processed with matching valid size
        if os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
            print(f"  [{idx:02d}/{total:02d}] Scene {scene_id:02d} cached ({s['duration']:.2f}s). Skipping...")
            processed_clips.append(out_path)
            continue
            
        print(f"  [{idx:02d}/{total:02d}] Processing Scene {scene_id:02d} ({s['tipo'].upper()}, {s['duration']:.2f}s)...")
        success = process_single_scene(s, source_asset, out_path, ffmpeg_path)
        if not success:
            raise RuntimeError(f"Failed to process scene {scene_id} ({source_asset})")
            
        processed_clips.append(out_path)
        
    return processed_clips
