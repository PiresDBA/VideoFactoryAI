"""
MediaAgent — Intelligent Multi-Source Media Acquisition Engine.

Priority chain per scene:
  1. Local cache (videos/ or imagens/) — skip if already downloaded
  2. Pixabay API — stock videos and images
  3. Wikimedia Commons — historical archival photographs
  4. Pollinations AI — free generative image (1920x1080)
  5. DALL-E 3 — optional, when OPENAI_API_KEY is set
  6. PIL Procedural Fallback — guaranteed render, never blocks pipeline
"""
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional
from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext
from videofactory.tools.media_sources import (
    query_pixabay,
    query_wikimedia_archive,
    generate_pollinations_ai_image,
    generate_dalle3_image,
    generate_procedural_fallback_image,
    download_binary,
)

# ─── Fallback Pixabay query banks ─────────────────────────────────────────────
VIDEO_FALLBACKS = [
    "geopolitics world news documentary footage",
    "city skyline aerial cinematic",
    "world map globe rotating politics",
    "parliament government building architecture",
    "people walking urban street documentary",
]
IMAGE_FALLBACKS = [
    "vintage historical archive black white documentary",
    "middle east historical photograph archive",
    "diplomatic meeting historical photograph",
    "protest crowd historical black white",
]

MIN_ASSET_SIZE = 15_000  # 15 KB minimum


def _local_path(scene: Dict[str, Any], videos_dir: str, imagens_dir: str) -> str:
    """Return expected local path for a scene's media file."""
    is_video = scene["tipo"] == "video"
    target_dir = videos_dir if is_video else imagens_dir
    return str(Path(target_dir) / scene["arquivo"])


def _asset_is_valid(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) >= MIN_ASSET_SIZE


class MediaAgent(BaseAgent):
    """Sources and downloads all scene media from multiple providers."""

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        if not context.scenes:
            raise ValueError("MediaAgent: storyboard vazio — rode o StoryboardAgent primeiro.")

        videos_dir = str(self.config.videos_dir)
        imagens_dir = str(self.config.imagens_dir)
        pixabay_key = self.config.pixabay_api_key
        openai_key = self.config.openai_api_key

        asset_map: Dict[int, str] = {}
        total = len(context.scenes)

        for idx, scene in enumerate(context.scenes, 1):
            scene_id = scene["id"]
            is_video = scene["tipo"] == "video"
            dest_path = _local_path(scene, videos_dir, imagens_dir)

            print(f"\n  [MediaAgent] Cena {idx}/{total} | tipo={scene['tipo']} | ID={scene_id:02d}")

            # ── 1. Local cache ─────────────────────────────────────────────────
            if _asset_is_valid(dest_path):
                self.log(f"Cache hit: {Path(dest_path).name}")
                asset_map[scene_id] = dest_path
                continue

            success = False

            # ── 2. Pixabay ─────────────────────────────────────────────────────
            if not scene.get("needs_ai_generation") and scene.get("query_en"):
                url = query_pixabay(scene["query_en"], is_video=is_video, api_key=pixabay_key)
                if url:
                    self.log(f"Pixabay → baixando {'vídeo' if is_video else 'imagem'}...")
                    success = download_binary(url, dest_path, min_size=MIN_ASSET_SIZE)
                    if success:
                        self.log(f"Pixabay OK: {Path(dest_path).name}", level="SUCCESS")

                # Pixabay fallback queries
                if not success:
                    fallbacks = VIDEO_FALLBACKS if is_video else IMAGE_FALLBACKS
                    for fb in fallbacks:
                        url = query_pixabay(fb, is_video=is_video, api_key=pixabay_key)
                        if url:
                            success = download_binary(url, dest_path, min_size=MIN_ASSET_SIZE)
                            if success:
                                self.log(f"Pixabay fallback OK: '{fb}'", level="SUCCESS")
                                break

            # ── 3. Wikimedia Commons (historical images) ───────────────────────
            if not success and not is_video and scene.get("query_en"):
                self.log("Tentando Wikimedia Commons...")
                url = query_wikimedia_archive(scene["query_en"])
                if url:
                    success = download_binary(url, dest_path, min_size=MIN_ASSET_SIZE)
                    if success:
                        self.log("Wikimedia OK", level="SUCCESS")

            # ── 4. Pollinations AI Image Generation ────────────────────────────
            if not success and not is_video:
                prompt = scene.get("ai_prompt") or scene.get("descricao") or scene["text"][:120]
                self.log(f"Gerando imagem IA via Pollinations: '{prompt[:60]}...'")
                success = generate_pollinations_ai_image(prompt, dest_path)
                if success:
                    self.log("Pollinations AI OK", level="SUCCESS")

            # ── 5. DALL-E 3 (if key available and image still missing) ─────────
            if not success and not is_video and openai_key:
                prompt = scene.get("ai_prompt") or scene.get("descricao") or scene["text"][:120]
                self.log("Gerando imagem IA via DALL-E 3...")
                success = generate_dalle3_image(prompt, dest_path, api_key=openai_key)
                if success:
                    self.log("DALL-E 3 OK", level="SUCCESS")

            # ── 6. Video-as-image fallback: generate still for video scenes ────
            if not success and is_video:
                # Convert to image scene for this failure case
                img_dest = dest_path.replace(".mp4", ".jpg")
                prompt = scene.get("query_en") or scene.get("descricao") or "documentary footage"
                self.log(f"Fallback vídeo → gerando imagem IA para cena de vídeo...")
                success = generate_pollinations_ai_image(prompt, img_dest)
                if success:
                    dest_path = img_dest
                    context.scenes[idx - 1]["tipo"] = "image"
                    context.scenes[idx - 1]["arquivo"] = Path(img_dest).name
                    self.log(f"Cena {scene_id} convertida para imagem IA.", level="SUCCESS")

            # ── 7. PIL Procedural last resort ─────────────────────────────────
            if not success:
                img_dest = dest_path if not is_video else dest_path.replace(".mp4", ".jpg")
                self.log(f"Usando fallback procedural PIL para cena {scene_id}", level="WARN")
                generate_procedural_fallback_image(
                    title=scene.get("descricao", f"Cena {scene_id}")[:60],
                    subtitle=scene["text"][:80],
                    dest_path=img_dest
                )
                dest_path = img_dest
                context.scenes[idx - 1]["tipo"] = "image"
                context.scenes[idx - 1]["arquivo"] = Path(img_dest).name

            asset_map[scene_id] = dest_path

            # Rate limiting between API calls
            time.sleep(0.3)

        context.asset_map = asset_map
        self.log(f"Mídia adquirida para {len(asset_map)}/{total} cenas.", level="SUCCESS")
        return context
