"""
Intelligent Multi-Source Media Sourcing Tool for VideoFactoryAI.
Integrates:
1. Pixabay API (Stock videos & images)
2. Wikimedia Commons API (Verified historical archival photographs)
3. Pollinations AI (Zero-cost photorealistic AI image generation in 1920x1080)
4. OpenAI DALL-E 3 (Optional)
5. Procedural PIL Fallback Generator (Guarantees zero failed renders)
"""
import os
import random
import urllib.parse
import requests
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

WIKIMEDIA_USER_AGENT = "VideoFactoryAI/2.0 (multimodal-documentary-pipeline; contact@videofactory.internal)"

def download_binary(url: str, dest_path: str, min_size: int = 5000, timeout: int = 25) -> bool:
    """Download binary content to file with minimum file size validation."""
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    try:
        resp = requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            return os.path.exists(dest_path) and os.path.getsize(dest_path) >= min_size
    except Exception as e:
        print(f"    [Download Error] {dest_path}: {e}")
    return False

def query_pixabay(query: str, is_video: bool, api_key: str) -> Optional[str]:
    """Search Pixabay API for HD stock video or image."""
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
                    vids = hits[0].get("videos", {})
                    for quality in ["large", "medium", "small"]:
                        if quality in vids and vids[quality].get("url"):
                            return vids[quality]["url"]
                else:
                    return hits[0].get("largeImageURL") or hits[0].get("webformatURL")
    except Exception as e:
        print(f"    [Pixabay Error] '{query}': {e}")
    return None

def query_wikimedia_archive(query: str) -> Optional[str]:
    """Search Wikimedia Commons API for authentic historical archival photographs."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "format": "json"
    }
    headers = {"User-Agent": WIKIMEDIA_USER_AGENT}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        pages = r.json().get("query", {}).get("pages", {})
        for _, p in pages.items():
            ii_list = p.get("imageinfo", [])
            if ii_list:
                ii = ii_list[0]
                mime = ii.get("mime", "")
                if mime in ["image/jpeg", "image/png"]:
                    return ii.get("url")
    except Exception as e:
        print(f"    [Wikimedia Error] '{query}': {e}")
    return None

def generate_pollinations_ai_image(
    prompt: str,
    dest_path: str,
    width: int = 1920,
    height: int = 1080,
    seed: Optional[int] = None
) -> bool:
    """Generate high-resolution AI image via Pollinations.ai API."""
    if seed is None:
        seed = random.randint(100000, 999999)
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&seed={seed}"
    return download_binary(url, dest_path, min_size=15000, timeout=35)

def generate_dalle3_image(
    prompt: str,
    dest_path: str,
    api_key: Optional[str] = None
) -> bool:
    """Generate AI image using OpenAI DALL-E 3."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        response = client.images.generate(
            model="dall-e-3",
            prompt=f"Cinematic historical documentary style, 16:9 widescreen, ultra detailed, photorealistic: {prompt}",
            size="1792x1024",
            quality="standard",
            n=1
        )
        image_url = response.data[0].url
        return download_binary(image_url, dest_path, min_size=20000)
    except Exception as e:
        print(f"    [DALL-E 3 Error] {e}")
        return False

def generate_procedural_fallback_image(
    title: str,
    subtitle: str,
    dest_path: str,
    width: int = 1920,
    height: int = 1080
) -> bool:
    """Generate a clean cinematic gradient card with typography if all network sources fail."""
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Gradient overlay
    for y in range(height):
        ratio = y / height
        r = int(15 * (1 - ratio) + 30 * ratio)
        g = int(23 * (1 - ratio) + 41 * ratio)
        b = int(42 * (1 - ratio) + 59 * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Center title box
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    draw.text((100, height // 2 - 40), title, fill=(240, 240, 240), font=font)
    draw.text((100, height // 2 + 10), subtitle, fill=(180, 180, 180), font=font)

    img.save(dest_path, "JPEG", quality=90)
    return os.path.exists(dest_path)
