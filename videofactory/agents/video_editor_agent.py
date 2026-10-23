"""
VideoEditorAgent — FFmpeg Clip Processing, Assembly & Thumbnail Generation.

Responsabilities:
  • Apply Ken Burns zoompan to all image scenes
  • Normalize all video scenes to 1920x1080 @30fps
  • Concatenate processed clips via FFmpeg concat demuxer
  • Bind narration audio and burn Whisper SRT subtitles
  • Generate the final MP4 video file and a 1280x720 JPEG thumbnail
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image
from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext
from videofactory.tools.ffmpeg_tool import (
    render_ken_burns_clip,
    normalize_video_clip,
    create_concat_manifest,
    assemble_master_video,
)

MIN_CLIP_SIZE = 50_000  # 50 KB minimum for cached clip validation


def _generate_thumbnail(
    first_asset: str,
    output_path: str,
    title: str,
    width: int = 1280,
    height: int = 720
) -> bool:
    """Create a 1280x720 YouTube-style thumbnail from the first scene asset."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Open and resize base image
        if first_asset.lower().endswith((".jpg", ".jpeg", ".png")):
            img = Image.open(first_asset).convert("RGB")
        else:
            # Attempt to extract frame from video using PIL fallback
            img = Image.new("RGB", (width, height), (15, 23, 42))

        img = img.resize((width, height), Image.LANCZOS)
        draw = ImageDraw.Draw(img)

        # Semi-transparent dark gradient at bottom
        for y in range(height // 2, height):
            alpha = int(220 * (y - height // 2) / (height // 2))
            r, g, b = img.getpixel((width // 2, y))
            new_r = int(r * (1 - alpha / 255))
            new_g = int(g * (1 - alpha / 255))
            new_b = int(b * (1 - alpha / 255))
            draw.line([(0, y), (width, y)], fill=(new_r, new_g, new_b))

        # Title text
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        # Wrap long title
        max_chars = 50
        words = title.split()
        lines, current = [], ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars:
                current += (" " if current else "") + word
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        y_start = height - len(lines) * 30 - 20
        for line in lines:
            draw.text((30, y_start), line, fill=(255, 255, 255), font=font)
            y_start += 30

        img.save(output_path, "JPEG", quality=92)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"  [Thumbnail Error] {e}")
        return False


class VideoEditorAgent(BaseAgent):
    """Processes all scenes into clips and renders the final documentary."""

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        if not context.scenes:
            raise ValueError("VideoEditorAgent: storyboard vazio.")
        if not context.asset_map:
            raise ValueError("VideoEditorAgent: nenhuma mídia disponível — rode o MediaAgent primeiro.")
        if not context.audio_path or not os.path.exists(context.audio_path):
            raise FileNotFoundError("VideoEditorAgent: narração ausente.")
        if not context.srt_path or not os.path.exists(context.srt_path):
            raise FileNotFoundError("VideoEditorAgent: SRT de legenda ausente.")

        temp_clips_dir = str(self.config.temp_clips_dir)
        os.makedirs(temp_clips_dir, exist_ok=True)

        ffmpeg = self.config.ffmpeg_path
        total = len(context.scenes)
        processed_clips: List[str] = []

        # ── 1. Process each scene ─────────────────────────────────────────────
        for idx, scene in enumerate(context.scenes, 1):
            scene_id = scene["id"]
            source_asset = context.asset_map.get(scene_id)

            if not source_asset or not os.path.exists(source_asset):
                raise FileNotFoundError(
                    f"VideoEditorAgent: asset da cena {scene_id} não encontrado: {source_asset}"
                )

            out_filename = f"clip_{scene_id:02d}.mp4"
            out_path = str(Path(temp_clips_dir) / out_filename)

            # Cache check
            if os.path.exists(out_path) and os.path.getsize(out_path) > MIN_CLIP_SIZE:
                print(f"  [{idx:02d}/{total:02d}] Clip {scene_id:02d} em cache. Pulando...")
                processed_clips.append(out_path)
                # Update context back-reference
                context.scenes[idx - 1]["processed_clip"] = out_path
                continue

            duration = scene.get("duration", self.config.target_scene_duration)
            duration = max(float(duration), self.config.min_scene_duration)

            print(f"  [{idx:02d}/{total:02d}] Processando cena {scene_id:02d} ({scene['tipo'].upper()}, {duration:.2f}s)...")

            if scene["tipo"] == "image":
                success = render_ken_burns_clip(
                    image_path=source_asset,
                    output_clip_path=out_path,
                    duration=duration,
                    ffmpeg_path=ffmpeg,
                    width=self.config.width,
                    height=self.config.height,
                    fps=self.config.fps,
                    zoom_speed=self.config.ken_burns_zoom_speed,
                    scene_index=scene_id,
                )
            else:
                success = normalize_video_clip(
                    video_path=source_asset,
                    output_clip_path=out_path,
                    duration=duration,
                    ffmpeg_path=ffmpeg,
                    width=self.config.width,
                    height=self.config.height,
                    fps=self.config.fps,
                )

            if not success:
                raise RuntimeError(f"VideoEditorAgent: falha ao processar cena {scene_id}.")

            processed_clips.append(out_path)
            context.scenes[idx - 1]["processed_clip"] = out_path

        context.processed_clips = processed_clips

        # ── 2. Create concat manifest ─────────────────────────────────────────
        manifest_path = str(self.config.root_dir / "concat_list.txt")
        create_concat_manifest(processed_clips, manifest_path)
        context.manifest_path = manifest_path
        self.log(f"Manifest de concatenação gerado ({len(processed_clips)} clipes)")

        # ── 3. Render master video ─────────────────────────────────────────────
        output_path = str(self.config.saida_dir / "documentario_final.mp4")
        self.log("Iniciando renderização master com FFmpeg...")
        success = assemble_master_video(
            manifest_path=manifest_path,
            audio_path=context.audio_path,
            srt_path=context.srt_path,
            output_path=output_path,
            ffmpeg_path=ffmpeg,
            font_size=self.config.subtitle_font_size,
            margin_v=self.config.subtitle_margin_v,
            crf=self.config.crf,
            preset=self.config.preset,
        )

        if not success:
            raise RuntimeError("VideoEditorAgent: renderização do vídeo master falhou.")

        context.output_video_path = output_path
        self.log(f"Vídeo master gerado: '{Path(output_path).name}'", level="SUCCESS")

        # ── 4. Generate Thumbnail ──────────────────────────────────────────────
        thumb_path = str(self.config.saida_dir / "thumbnail.jpg")
        first_asset = context.asset_map.get(context.scenes[0]["id"], "")
        thumb_ok = _generate_thumbnail(
            first_asset=first_asset,
            output_path=thumb_path,
            title=context.title
        )
        if thumb_ok:
            context.output_thumbnail_path = thumb_path
            self.log(f"Thumbnail gerada: '{Path(thumb_path).name}'", level="SUCCESS")
        else:
            self.log("Thumbnail não pôde ser gerada.", level="WARN")

        return context
