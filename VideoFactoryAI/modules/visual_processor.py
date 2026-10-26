"""
Advanced Visual Processing & Motion Engineering
Standardizes all video clips and generates professional motion effects on static images.

Effects available:
- pan: Smooth horizontal/vertical pan across the image
- slide: Slide transition from one side to another
- static: No motion (just normalized)
"""
import os
import random
import subprocess
import unicodedata
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

EFFECT_TYPES = ["pan", "slide", "static"]
DEFAULT_EFFECT = "pan"


def get_effect_for_scene(scene: Dict[str, Any], cfg: Dict, scene_idx: int) -> str:
    """Determine the best effect for a scene based on content and configuration."""
    # Check config for forced effect
    forced = cfg.get("video", {}).get("default_image_effect")
    if forced and forced in EFFECT_TYPES and forced != "auto":
        return forced
    
    # Auto mode: cycle through effects for variety
    effects_cycle = EFFECT_TYPES
    return effects_cycle[scene_idx % len(effects_cycle)]


def build_pan_filter(duration: float, fps: int = 30, direction: Optional[str] = None) -> str:
    """
    Build a smooth pan filter using scale + crop with overlay.
    The pan remains smooth without applying a zoom.
    """
    frames = max(1, int(round(duration * fps)))
    
    # Directions: left_to_right, right_to_left, top_to_bottom, bottom_to_top, diagonal
    directions = ["left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top", "diagonal_tl_br", "diagonal_tr_bl"]
    if direction is None:
        direction = random.choice(directions)
    
    # Scale to 4K for sub-pixel precision, then crop to 1080p moving across
    # The crop window moves across the 4K image
    if direction == "left_to_right":
        crop_expr = f"crop=1920:1080:x='min(iw-1920, (iw-1920)*n/{frames})':y=(ih-1080)/2"
    elif direction == "right_to_left":
        crop_expr = f"crop=1920:1080:x='max(0, (iw-1920)*(1-n/{frames}))':y=(ih-1080)/2"
    elif direction == "top_to_bottom":
        crop_expr = f"crop=1920:1080:x=(iw-1920)/2:y='min(ih-1080, (ih-1080)*n/{frames})'"
    elif direction == "bottom_to_top":
        crop_expr = f"crop=1920:1080:x=(iw-1920)/2:y='max(0, (ih-1080)*(1-n/{frames}))'"
    elif direction == "diagonal_tl_br":
        crop_expr = f"crop=1920:1080:x='min(iw-1920, (iw-1920)*n/{frames})':y='min(ih-1080, (ih-1080)*n/{frames})'"
    else:  # diagonal_tr_bl
        crop_expr = f"crop=1920:1080:x='max(0, (iw-1920)*(1-n/{frames}))':y='min(ih-1080, (ih-1080)*n/{frames})'"
    
    vf = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"{crop_expr},"
        f"fps={fps},format=yuv420p"
    )
    return vf


def build_slide_filter(duration: float, fps: int = 30, direction: Optional[str] = None, scene_idx: int = 0) -> str:
    """Return a safe static-normalization fallback for callers using -vf.

    The animated slide is constructed with a separate filter_complex graph in
    process_single_scene because overlay animation requires a background input.
    This function remains available for compatibility with any external caller.
    """
    return (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={fps},format=yuv420p"
    )


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
            # A proper overlay graph: black canvas + animated image. The prior
            # implementation placed `x=`/`y=` as if they were filters, which
            # FFmpeg rejects (e.g. "[slide]x=...").
            frames = max(2, int(round(float(duration) * 30)))
            directions = ["left", "right", "up", "down"]
            direction = directions[scene_idx % len(directions)]
            if direction == "left":
                x_expr, y_expr = f"-overlay_w+overlay_w*n/{frames - 1}", "0"
            elif direction == "right":
                x_expr, y_expr = f"main_w-main_w*n/{frames - 1}", "0"
            elif direction == "up":
                x_expr, y_expr = "0", f"-overlay_h+overlay_h*n/{frames - 1}"
            else:  # down
                x_expr, y_expr = "0", f"main_h-main_h*n/{frames - 1}"

            filter_complex = (
                "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[img];"
                f"[1:v][img]overlay=x={x_expr}:y={y_expr}:shortest=1,"
                "fps=30,format=yuv420p[out]"
            )
            cmd = [
                ffmpeg_path, "-y",
                "-loop", "1", "-i", source_asset,
                "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:r=30:d={duration}",
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-an", output_clip_path
            ]
        else:
            if effect == "pan":
                vf_filter = build_pan_filter(duration)
            else:  # static
                vf_filter = (
                    "scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
                    "fps=30,format=yuv420p"
                )

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

    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=300)
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
            else:
                x = (3840 - target_w) // 2
                y = (2160 - target_h) // 2

            crop = frame_4k[y:y+target_h, x:x+target_w]
            out.write(crop)
        
        out.release()
        cap.release()
        return os.path.exists(output_clip_path) and os.path.getsize(output_clip_path) > 1000
        
    except Exception as e:
        print(f"    [OpenCV Error] {e}")
        return False


def _create_missing_scene_card(scene: Dict[str, Any], output_path: str) -> None:
    """Create an explicit visual placeholder so a missing asset cannot shorten the timeline."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1920, 1080), (24, 34, 52))
    draw = ImageDraw.Draw(image)
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
    using_default_font = False
    try:
        heading_font = ImageFont.truetype(str(font_path), 58)
        body_font = ImageFont.truetype(str(font_path), 38)
    except OSError:
        heading_font = body_font = ImageFont.load_default()
        using_default_font = True

    heading = f"SCENE {int(scene['id']):02d} - MEDIA UNAVAILABLE"
    description = str(
        scene.get("texto") or scene.get("descricao") or scene.get("query") or ""
    ).strip()
    if not description:
        description = "No visual asset was available for this scene."

    if using_default_font:
        heading = unicodedata.normalize("NFKD", heading).encode("ascii", "ignore").decode("ascii")
        description = unicodedata.normalize(
            "NFKD", description
        ).encode("ascii", "ignore").decode("ascii")

    draw.rectangle((100, 300, 1820, 305), fill=(74, 144, 226))
    draw.text((100, 355), heading, fill=(245, 247, 250), font=heading_font)

    lines = []
    current = ""
    for word in description.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=body_font)[2] > 1700:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for index, line in enumerate(lines[:8]):
        draw.text((100, 470 + index * 62), line, fill=(210, 218, 230), font=body_font)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "JPEG", quality=90)


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
        out_path = os.path.join(temp_clips_dir, f"clip_{scene_id:02d}.mp4")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
            print(f"  [{idx:02d}/{total:02d}] Scene {scene_id:02d} cached ({s['duration']:.2f}s). Skipping...")
            processed_clips.append(out_path)
            continue

        source_asset = asset_map.get(scene_id)
        scene_to_process = s
        fallback_used = False
        if not source_asset or not os.path.exists(source_asset):
            fallback = cfg.get("fallback_image")
            if fallback and os.path.exists(fallback):
                source_asset = str(fallback)
                scene_to_process = dict(s)
                scene_to_process["tipo"] = "image"
                fallback_used = True
            else:
                source_asset = os.path.join(
                    temp_clips_dir, f"fallback_scene_{scene_id:02d}.jpg"
                )
                scene_to_process = dict(s)
                scene_to_process["tipo"] = "image"
                fallback_used = True
        
        fallback_suffix = "_fallback" if fallback_used else ""
        out_filename = f"clip_{scene_id:02d}{fallback_suffix}.mp4"
        out_path = os.path.join(temp_clips_dir, out_filename)
        
        # Cache generated fallbacks separately from regular scene clips.
        if os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
            print(f"  [{idx:02d}/{total:02d}] Scene {scene_id:02d} cached ({s['duration']:.2f}s). Skipping...")
            processed_clips.append(out_path)
            continue

        if fallback_used and not (cfg.get("fallback_image") and os.path.isfile(source_asset)):
            _create_missing_scene_card(s, source_asset)
            print(
                f"  [WARN] Cena {scene_id:02d} sem mídia; usando cartão de fallback "
                "para preservar a duração."
            )
            
        print(
            f"  [{idx:02d}/{total:02d}] Processing Scene {scene_id:02d} "
            f"({scene_to_process['tipo'].upper()}, {s['duration']:.2f}s)..."
        )
        
        success = process_single_scene(scene_to_process, source_asset, out_path, ffmpeg_path, cfg, idx)
        
        # Fallback to OpenCV if FFmpeg fails and OpenCV available
        if not success and OPENCV_AVAILABLE and scene_to_process["tipo"] == "image":
            print(f"    [FFmpeg failed, trying OpenCV...]")
            success = process_single_scene_opencv(scene_to_process, source_asset, out_path, s["duration"])
        
        if not success:
            raise RuntimeError(f"Failed to process scene {scene_id} ({source_asset})")
            
        processed_clips.append(out_path)
    
    return processed_clips