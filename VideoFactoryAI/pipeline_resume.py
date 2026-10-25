"""Small, side-effect-free helpers for safe pipeline resume decisions."""

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


DEFAULT_IMAGE_MIN_BYTES = 15_000
DEFAULT_VIDEO_MIN_BYTES = 100_000
DEFAULT_AUDIO_MIN_BYTES = 10_000


def script_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def narration_hash_path(audio_path: os.PathLike | str) -> Path:
    return Path(f"{audio_path}.script.sha256")


def narration_cache_matches(
    audio_path: os.PathLike | str,
    script_text: str,
    minimum_bytes: int = DEFAULT_AUDIO_MIN_BYTES,
) -> bool:
    audio = Path(audio_path)
    hash_path = narration_hash_path(audio)
    if not audio.is_file() or audio.stat().st_size < minimum_bytes or not hash_path.is_file():
        return False
    try:
        stored_hash = hash_path.read_text(encoding="ascii").strip()
    except OSError:
        return False
    return stored_hash == script_sha256(script_text)


def save_narration_hash(audio_path: os.PathLike | str, script_text: str) -> None:
    hash_path = narration_hash_path(audio_path)
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    hash_path.write_text(script_sha256(script_text), encoding="ascii")


def build_resume_report(
    scenes: Iterable[Mapping[str, Any]],
    asset_map: Mapping[Any, str],
    image_min_bytes: int = DEFAULT_IMAGE_MIN_BYTES,
    video_min_bytes: int = DEFAULT_VIDEO_MIN_BYTES,
    asset_root: os.PathLike | str | None = None,
) -> Dict[str, Any]:
    pending = []
    completed = 0
    scene_list = list(scenes)
    for scene in scene_list:
        scene_id = scene.get("id")
        asset_path = asset_map.get(scene_id)
        if not asset_path and asset_root:
            media_dir = "videos" if str(scene.get("tipo", "image")).lower().startswith("video") else "imagens"
            filename = str(scene.get("arquivo", "") or "")
            if filename:
                asset_path = str(Path(asset_root) / media_dir / filename)
        minimum_bytes = (
            video_min_bytes
            if str(scene.get("tipo", "image")).lower().startswith("video")
            else image_min_bytes
        )
        if asset_path and Path(asset_path).is_file() and Path(asset_path).stat().st_size >= minimum_bytes:
            completed += 1
        else:
            pending.append(scene_id)
    return {
        "total": len(scene_list),
        "completed": completed,
        "pending": len(pending),
        "pending_scene_ids": pending,
        "to_process": len(pending),
    }
