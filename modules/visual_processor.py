"""
Advanced Visual Processing & Motion Engineering
Standardizes all video clips and generates professional motion effects on static images.

Effects available:
- pan: Smooth horizontal/vertical pan across the image
- ken_burns_smooth: Subtle zoom with smooth easing (no jitter)
- slide: Slide transition from one side to another
- fade_zoom: Subtle zoom with fade in/out
- static: No motion (just normalized)
"""
import os
import random
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# Try to import optional libraries for enhanced effects
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

try:
    from moviepy.editor import ImageClip, VideoFileClip, CompositeVideoClip
    from moviepy.video.fx.all import resize, crop, headblur
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

EFFECT_TYPES = ["pan", "ken_burns_smooth", "slide", "fade_zoom", "static"]
DEFAULT_EFFECT = "pan"


def get_effect_for_scene(scene: Dict[str, Any], cfg: Dict, scene_idx: int) -> str:
    """Determine the best effect for a scene based on content and configuration."""
    # Check config for forced effect
    forced = cfg.get("video", {}).get("default_image_effect")
    if forced and forced in EFFECT_TYPES and forced != "auto":
        return forced
    
    # Auto mode: cycle through effects for variety
    effects_cycle = ["pan", "ken_burns_smooth", "slide", "fade_zoom"]
    return effects_cycle[scene_idx % len(effects_cycle)]


def build_pan_filter(duration: float, fps: int = 30, direction: Optional[str] = None) -> str:
    """
    Build a smooth pan filter using scale + crop with overlay.
    This is much smoother than zoompan.
    """
    frames = max(1, int(round(duration * fps)))
    
    # Directions: left_to_right, right_to_left, top_to_bottom, bottom_to_top, diagonal
    directions = ["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top", "diagonal_tl_br", "diagonal_tr_bl"]
    if direction is None:
        direction = random.choice(directions)
    
    # Scale to 4K for sub-pixel precision, then crop to 1080p moving across
    # The crop window moves across the 4K image
    if direction == "left_to_right":
        crop_expr = f"crop=1920:1080:x='min(iw-1920, (iw-1920)*on/{frames})':y=(ih-1080)/2"
    elif direction == "right_to_left":
        crop_expr = f"crop=1920:1080:x='max(0, (iw-1920)*(1-on/{frames}))':y=(ih-1080)/2"
    elif direction == "top_to_bottom":
        crop_expr = f"crop=1920:1080:x=(iw-1920)/2:y='min(ih-1080, (ih-1080)*on/{frames})'"
    elif direction == "bottom_to_top":
        crop_expr = f"crop=1920:1080:x=(iw-1920)/2:y='max(0, (ih-1080)*(1-on/{frames}))'"
    elif direction == "diagonal_tl_br":
        crop_expr = f"crop=1920:1080:x='min(iw-1920, (iw-1920)*on/{frames})':y='min(ih-1080, (ih-1080)*on/{frames})'"
    else:  # diagonal_tr_bl
        crop_expr = f"crop=1920:1080:x='max(0, (iw-1920)*(1-on/{frames}))':y='min(ih-1080, (ih-1080)*on/{frames})'"
    
    vf = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"{crop_expr},"
        f"fps={fps},format=yuv420p"
    )
    return vf


def build_ken_burns_smooth_filter(duration: float, fps: int = 30, zoom_range: float = 0.08) -> str:
    """
    Build a truly smooth Ken Burns effect using scale + crop with easing.
    No zoompan - uses scale + crop with smooth interpolation.
    """
    frames = max(1, int(round(duration * fps)))
    
    # Subtle zoom range (e.g., 1.0 to 1.08)
    # Use smoothstep easing: 3t² - 2t³
    zoom_expr = f"1.0+{zoom_range}*(3*pow(on/{frames},2)-2*pow(on/{frames},3))"
    
    # Randomly choose zoom in or out
    if random.choice([True, False]):
        # Zoom in: 1.0 -> 1.08
        zoom_expr = f"1.0+{zoom_range}*(3*pow(on/{frames},2)-2*pow(on/{frames},3))"
    else:
        # Zoom out: 1.08 -> 1.0
        zoom_expr = f"1.0+{zoom_range}-{zoom_range}*(3*pow(on/{frames},2)-2*pow(on/{frames},3))"
    
    vf = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"zoompan=z='{zoom_expr}':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s=1920x1080:fps=30,format=yuv420p"
    )
    return vf


def build_slide_filter(duration: float, fps: int = 30, direction: Optional[str] = None, scene_idx: int = 0) -> str:
    """
    Build a filter_complex graph for a slide transition from a black canvas.
    """
    frames = max(1, int(round(duration * fps)))
    directions = ["left", "right", "up", "down"]
    if direction is None:
        direction = directions[scene_idx % len(directions)]
    
    # A secondary black input is supplied by process_single_scene.
    if direction == "left":
        x_expr, y_expr = f"-overlay_w+overlay_w*n/{max(1, frames - 1)}", "0"
    elif direction == "right":
        x_expr, y_expr = f"main_w-main_w*n/{max(1, frames - 1)}", "0"
    elif direction == "up":
        x_expr, y_expr = "0", f"-overlay_h+overlay_h*n/{max(1, frames - 1)}"
    else:
        x_expr, y_expr = "0", f"main_h-main_h*n/{max(1, frames - 1)}"
    return (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[img];"
        f"[1:v][img]overlay=x={x_expr}:y={y_expr}:shortest=1,"
        f"fps={fps},format=yuv420p[out]"
    )


def build_fade_zoom_filter(duration: float, fps: int = 30) -> str:
    """
    Subtle zoom with fade in/out - very professional looking.
    """
    frames = max(1, int(round(duration * fps)))
    
    # Fade in at start, subtle zoom, fade out at end
    fade_in = f"fade=in:0:30"
    fade_out = f"fade=out:{frames-30}:30"
    zoom_expr = "1.0+0.04*(3*pow(on/{f},2)-2*pow(on/{f},3))".format(f=frames)
    
    vf = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"zoompan=z='1.0+0.04*(3*pow(on/{frames},2)-2*pow(on/{frames},3))':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s=1920x1080:fps=30,"
        f"{fade_in},{fade_out},format=yuv420p"
    )
    return vf


def process_single_scene(
    scene: Dict[str, Any],
    source_asset: str,
    output_clip_path: str,
    ffmpeg_path: str,
    cfg: Dict,
    scene_idx: int = 0
) -> bool:
    """Normalize a single image or video asset to 1920x1080@30fps with professional motion."""
    scene_id = scene["id"]
    duration = scene["duration"]
    is_image = (scene["tipo"] == "image")
    
    # Check cache
    if os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 50000:
        return True
    
    # Determine effect
    effect = get_effect_for_scene(scene, cfg, scene_idx)
    print(
        f"  [Scene {scene_id:02d}] Duração: {float(duration):.2f}s | "
        f"Tipo: {scene.get('tipo', 'image')} | Efeito: {effect} | "
        f"Asset: {Path(source_asset).name}"
    )
    
    if is_image:
        if effect == "slide":
            filter_complex = build_slide_filter(duration, scene_idx=scene_idx)
            cmd = [
                ffmpeg_path, "-y",
                "-loop", "1", "-i", source_asset,
                "-f", "lavfi", "-i",
                f"color=c=black:s=1920x1080:r=30:d={duration}",
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",
                output_clip_path,
            ]
        elif effect == "pan":
            vf_filter = build_pan_filter(duration)
        elif effect == "ken_burns_smooth":
            vf_filter = build_ken_burns_smooth_filter(duration)
        elif effect == "fade_zoom":
            vf_filter = build_fade_zoom_filter(duration)
        else:  # static
            vf_filter = (
                f"scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps=30,format=yuv420p"
            )
        
        if effect != "slide":
            cmd = [
                ffmpeg_path, "-y",
                "-loop", "1",
                "-i", source_asset,
                "-vf", vf_filter,
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",
                output_clip_path
            ]
    else:
        # Video Normalization
        vf_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
            "fps=30,format=yuv420p"
        )
        cmd = [
            ffmpeg_path, "-y",
            "-stream_loop", "-1",
            "-i", source_asset,
            "-vf", vf_filter,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            output_clip_path
        ]
    
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=300)
    if res.returncode != 0:
        print(f"    [FFmpeg Error] Scene {scene_id} (effect={effect}): {res.stderr[-500:]}")
        return False
        
    return os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000


def process_single_scene_opencv(
    scene: Dict[str, Any],
    source_asset: str,
    output_clip_path: str,
    duration: float,
    effect: str = "pan"
) -> bool:
    """
    Alternative implementation using OpenCV for extremely smooth motion.
    Only used if OpenCV is available and FFmpeg fails.
    """
    if not OPENCV_AVAILABLE:
        return False
    
    try:
        cap = cv2.VideoCapture(source_asset)
        if not cap.isOpened():
            return False
        
        # Read first frame (for images, this is the only frame)
        ret, frame = cap.read()
        if not ret:
            return False
        
        h, w = frame.shape[:2]
        target_w, target_h = 1920, 1080
        fps = 30
        total_frames = int(duration * 30)
        
        # Resize frame to 4K for sub-pixel motion
        frame_4k = cv2.resize(frame, (3840, 2160), interpolation=cv2.INTER_LANCZOS4)
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_clip_path, fourcc, fps, (target_w, target_h))
        
        for i in range(total_frames):
            t = i / max(1, total_frames - 1)
            # Smoothstep easing
            eased = 3 * t * t - 2 * t * t * t
            
            if effect == "pan":
                # Pan across the image
                x = int((3840 - target_w) * eased)
                y = int((2160 - target_h) * 0.5)
            elif effect == "ken_burns_smooth":
                zoom = 1.0 + 0.08 * (3 * t * t - 2 * t * t * t)
                new_w = int(target_w / zoom)
                new_h = int(target_h / zoom)
                x = int((3840 - new_w) * 0.5)
                y = int((2160 - new_h) * 0.5)
                crop = frame_4k[y:y+new_h, x:x+new_w]
                frame_out = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
                out.write(frame_out)
                continue
            
            crop = frame_4k[y:y+target_h, x:x+target_w]
            out.write(crop)
        
        out.release()
        cap.release()
        return os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000
        
    except Exception as e:
        print(f"    [OpenCV Error] {e}")
        return False


def process_all_scenes(
    scenes: List[Dict[str, Any]],
    asset_map: Dict[int, str],
    temp_clips_dir: str,
    ffmpeg_path: str,
    cfg: Dict
) -> List[str]:
    """Process and normalize all scenes sequentially into standardized clips."""
    os.makedirs(temp_clips_dir, exist_ok=True)
    processed_clips = []
    
    total = len(scenes)
    for idx, s in enumerate(scenes, 1):
        scene_id = s["id"]
        source_asset = asset_map.get(scene_id)
        scene_to_process = s
        if not source_asset or not os.path.exists(source_asset):
            fallback = cfg.get("fallback_image")
            if fallback and os.path.isfile(fallback):
                print(f"  [WARN] Scene {scene_id} asset missing; using fallback image.")
                source_asset = fallback
                scene_to_process = dict(s, tipo="image", arquivo=os.path.basename(fallback))
            else:
                print(f"  [WARN] Scene {scene_id} has no media; skipping.")
                continue
        
        out_filename = f"clip_{scene_id:02d}.mp4"
        out_path = os.path.join(temp_clips_dir, out_filename)
        
        # Check cache
        if os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
            print(f"  [{idx:02d}/{total:02d}] Scene {scene_id:02d} cached ({s['duration']:.2f}s). Skipping...")
            processed_clips.append(out_path)
            continue
            
        effect = get_effect_for_scene(scene_to_process, cfg, idx) if scene_to_process["tipo"] == "image" else "none"
        print(
            f"  [{idx:02d}/{total:02d}] Scene {scene_id:02d} | "
            f"Duração: {s['duration']:.2f}s | Tipo: {scene_to_process['tipo']} | "
            f"Efeito: {effect} | Asset: {os.path.basename(source_asset)}"
        )
        
        success = process_single_scene(scene_to_process, source_asset, out_path, ffmpeg_path, cfg, idx)
        
        # Fallback to OpenCV if FFmpeg fails and OpenCV available
        if not success and OPENCV_AVAILABLE and scene_to_process["tipo"] == "image":
            print(f"    [FFmpeg failed, trying OpenCV...]")
            success = process_single_scene_opencv(s, source_asset, out_path, s["duration"])
        
        if not success:
            raise RuntimeError(f"Failed to process scene {scene_id} ({source_asset})")
            
        processed_clips.append(out_path)
    
    return processed_clips