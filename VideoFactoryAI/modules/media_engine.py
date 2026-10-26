"""
Intelligent Semantic Media Sourcing Engine (Pixabay API & Fallbacks)
Fetches contextually matching videos and images for each scene.
"""
import os
import shutil
import subprocess
import json
from pathlib import Path
import requests
from typing import List, Dict, Any

API_KEY = "58184749-b92df4cd039274d2c7a6aac7a"

GENERIC_FALLBACK_QUERIES = {
    "video": ["politics diplomacy", "middle east desert", "geopolitics map", "city traffic crowd"],
    "image": ["vintage historical archive", "middle east vintage", "protest crowd historical", "diplomacy meeting"]
}

def get_media_info(media_path: str) -> Dict[str, Any]:
    """Return basic media metadata using ffprobe.

    Locates ffprobe next to FFmpeg first, then checks common project locations
    and PATH. Returns an empty/zero-valued result on probe failure so optional
    validation can report a useful warning instead of failing at import time.
    """
    path = Path(media_path).expanduser().resolve()
    candidates = []
    env_probe = os.getenv("FFPROBE_PATH")
    if env_probe:
        candidates.append(Path(env_probe))
    env_ffmpeg = os.getenv("FFMPEG_PATH")
    if env_ffmpeg:
        candidates.append(Path(env_ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe"))
    module_dir = Path(__file__).resolve().parent
    for base in (module_dir, module_dir.parent, module_dir.parent.parent):
        candidates.append(base / "ffmpeg" / "bin" / ("ffprobe.exe" if os.name == "nt" else "ffprobe"))
    which_probe = shutil.which("ffprobe")
    if which_probe:
        candidates.append(Path(which_probe))
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        candidates.append(Path(which_ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe"))

    probe = next((candidate for candidate in candidates if candidate.is_file()), None)
    if probe is None:
        return {"duration": 0.0, "width": 0, "height": 0, "streams": []}

    try:
        result = subprocess.run(
            [str(probe), "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return {"duration": 0.0, "width": 0, "height": 0, "streams": []}
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), {})
        try:
            duration = float(data.get("format", {}).get("duration", 0) or 0)
        except (TypeError, ValueError):
            duration = 0.0
        return {
            "duration": duration,
            "width": int(video.get("width", 0) or 0),
            "height": int(video.get("height", 0) or 0),
            "streams": streams,
        }
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return {"duration": 0.0, "width": 0, "height": 0, "streams": []}


def query_pixabay(query: str, is_video: bool, api_key: str = API_KEY) -> str:
    """Query Pixabay API for video or image and return the download URL or None."""
    endpoint = "https://pixabay.com/api/videos/" if is_video else "https://pixabay.com/api/"
    params = {
        "key": api_key,
        "q": query,
        "per_page": 5,
        "safesearch": "true"
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=12)
        if resp.status_code == 200:
            hits = resp.json().get("hits", [])
            if hits:
                if is_video:
                    # Choose large or medium video
                    vids = hits[0].get("videos", {})
                    for quality in ["large", "medium", "small"]:
                        if quality in vids and vids[quality].get("url"):
                            return vids[quality]["url"]
                else:
                    return hits[0].get("largeImageURL") or hits[0].get("webformatURL")
    except Exception as e:
        print(f"    [Pixabay Error] Query '{query}': {e}")
    return None

def download_file(url: str, dest_path: str) -> bool:
    """Download binary content to file."""
    try:
        resp = requests.get(url, stream=True, timeout=20)
        if resp.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            return os.path.exists(dest_path) and os.path.getsize(dest_path) > 5000
    except Exception as e:
        print(f"    [Download Error] {dest_path}: {e}")
    return False

def ensure_media_for_scenes(
    scenes: List[Dict[str, Any]],
    videos_dir: str,
    imagens_dir: str,
    api_key: str = API_KEY
) -> Dict[int, str]:
    """
    Ensure each scene has its corresponding media file in videos/ or imagens/.
    Returns a dictionary mapping scene_id to absolute file path.
    """
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(imagens_dir, exist_ok=True)
    
    # Pre-scan existing local fallback pools
    local_images = [os.path.join(imagens_dir, f) for f in os.listdir(imagens_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    local_videos = [os.path.join(videos_dir, f) for f in os.listdir(videos_dir) if f.lower().endswith('.mp4')]
    
    asset_map = {}
    
    for s in scenes:
        scene_id = s["id"]
        is_video = (s["tipo"] == "video")
        filename = s["arquivo"]
        target_dir = videos_dir if is_video else imagens_dir
        dest_path = os.path.join(target_dir, filename)
        
        # 1. Check if asset already exists and is non-empty
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000:
            print(f"  [Scene {scene_id:02d}] Asset already exists: {filename}")
            asset_map[scene_id] = dest_path
            continue
            
        # 2. Try Primary Query
        print(f"  [Scene {scene_id:02d}] Sourcing {'video' if is_video else 'image'} for '{s['query']}'...")
        media_url = query_pixabay(s["query"], is_video=is_video, api_key=api_key)
        
        # 3. Try Secondary/Fallback Queries if needed
        if not media_url:
            fallbacks = GENERIC_FALLBACK_QUERIES["video" if is_video else "image"]
            for fb_q in fallbacks:
                print(f"    -> Retrying with fallback: '{fb_q}'...")
                media_url = query_pixabay(fb_q, is_video=is_video, api_key=api_key)
                if media_url:
                    break
                    
        # 4. Download asset if URL was found
        success = False
        if media_url:
            success = download_file(media_url, dest_path)
            if success:
                print(f"    -> Successfully downloaded: {filename}")
                asset_map[scene_id] = dest_path
                continue
                
        # 5. Local Safe Fallback if API completely failed
        print(f"    -> Sourcing local fallback for scene {scene_id:02d}...")
        pool = local_videos if is_video else local_images
        if pool:
            src = pool[scene_id % len(pool)]
            shutil.copy(src, dest_path)
            print(f"    -> Copied local fallback from {os.path.basename(src)} to {filename}")
            asset_map[scene_id] = dest_path
        else:
            # If opposite pool exists
            alt_pool = local_images if is_video else local_videos
            if alt_pool:
                src = alt_pool[0]
                shutil.copy(src, dest_path)
                asset_map[scene_id] = dest_path
            else:
                raise RuntimeError(f"Critical error: No asset or fallback available for scene {scene_id}!")
                
    return asset_map
