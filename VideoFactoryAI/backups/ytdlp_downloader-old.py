# -*- coding: utf-8 -*-
"""
yt-dlp Video Downloader Module for VideoFactoryAI
Uses yt-dlp to search and download CC-licensed videos from multiple sources.
"""
import os
import re
import json
import subprocess
import sys
import importlib.util
from typing import Optional, Tuple, List, Dict
from pathlib import Path

# CC Licenses that allow commercial reuse
CC_ALLOWED_LICENSES = {
    "cc0",
    "cc-by",
    "cc-by-sa",
    "cc-by-nc",
    "cc-by-nc-sa",
    "public domain",
    "pd",
}

# License keywords that indicate CC-licensed content
CC_LICENSE_KEYWORDS = [
    "creativecommons",
    "creative commons",
    "cc-by",
    "cc-by-sa",
    "cc-by-nc",
    "cc-by-nc-sa",
    "cc0",
    "public domain",
    "publicdomain",
]

# Terms that indicate NON-CC content (exclude)
NON_CC_INDICATORS = [
    "standard youtube license",
    "standard license",
    "all rights reserved",
    "copyright",
    "no reuse",
    "no derivative",
]

# Module-level cache for yt-dlp availability check (using mutable container for proper closure)
_check_ytdlp_available_cache = [None]

def _check_ytdlp_available() -> bool:
    """Check if yt-dlp is installed and available.
    
    Uses a simple import check first (fast), falls back to subprocess check.
    Result is cached to avoid repeated checks.
    """
    # Return cached result if available
    if _check_ytdlp_available_cache[0] is not None:
        return _check_ytdlp_available_cache[0]
    
    try:
        # Fast path: try importing yt_dlp directly
        import yt_dlp
        _check_ytdlp_available_cache[0] = True
        return True
    except ImportError:
        pass
    
    try:
        # Fallback: subprocess check with current Python
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True, text=True, timeout=5
        )
        result_available = result.returncode == 0
    except Exception:
        result_available = False
    
    _check_ytdlp_available_cache[0] = result_available
    return result_available


def _extract_license_from_yt_metadata(info: dict) -> str:
    """Extract license info from yt-dlp metadata."""
    license_fields = [
        "license",
        "license_id", 
        "license_name",
        "availability",
        "availability.license",
        "availability.license_type",
        "license_name",
        "license_url",
    ]
    
    for field in license_fields:
        value = info
        try:
            for part in field.split("."):
                value = value.get(part) if isinstance(value, dict) else None
                if value is None:
                    break
            if value and isinstance(value, str) and value.strip():
                return value.lower().strip()
        except Exception:
            continue
    
    description = info.get("description", "") or ""
    desc_lower = description.lower()
    for kw in ["creative commons", "creative commons", "cc-by", "cc-by-sa", 
               "cc-by-nc", "cc-by-nc-sa", "cc0", "public domain", "publicdomain"]:
        if kw in desc_lower:
            return kw
    
    tags = info.get("tags", [])
    for tag in tags:
        tag_lower = tag.lower()
        if any(kw in tag_lower for kw in ["creativecommons", "creative commons", 
                                           "cc-by", "cc0", "public domain", "publicdomain"]):
            return tag
    return ""


def _is_cc_licensed(license_str: str, description: str = "") -> bool:
    """Check if content has a CC license allowing reuse."""
    combined = f"{license_str} {description}".lower()
    
    for indicator in NON_CC_INDICATORS:
        if indicator in combined:
            return False
    
    for keyword in CC_LICENSE_KEYWORDS:
        if keyword in combined:
            return True
    
    return False


def _search_youtube_cc(query: str, max_results: int = 10) -> List[Dict]:
    """Search YouTube for Creative Commons licensed videos using yt-dlp."""
    cmd = [
        "yt-dlp",
        f"ytsearch{max_results}:{query} creativecommons",
        "--flat-playlist",
        "--skip-download",
        "--print-json",
        "--no-warnings",
        "--ignore-errors",
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                video = json.loads(line)
                license_str = _extract_license_from_yt_metadata(video)
                if _is_cc_licensed(license_str, video.get("description", "")):
                    videos.append({
                        "id": video.get("id"),
                        "title": video.get("title"),
                        "url": f"https://www.youtube.com/watch?v={video.get('id')}",
                        "duration": video.get("duration"),
                        "license": license_str,
                        "uploader": video.get("uploader"),
                        "view_count": video.get("view_count"),
                    })
            except json.JSONDecodeError:
                continue
        return videos
    except subprocess.TimeoutExpired:
        print(f"    [yt-dlp] Timeout searching for '{query}'")
        return []
    except Exception as e:
        print(f"    [yt-dlp] Error searching: {e}")
        return []


def _download_with_ytdlp(video_url: str, dest: str, format_selector: str = None) -> bool:
    """Download a video using yt-dlp with specified format."""
    if format_selector is None:
        format_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    
    cmd = [
        "yt-dlp",
        "-f", format_selector,
        "-o", dest,
        "--no-warnings",
        "--ignore-errors",
        video_url,
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 100000
    except subprocess.TimeoutExpired:
        print(f"    [yt-dlp] Timeout downloading '{video_url}'")
        return False
    except Exception as e:
        print(f"    [yt-dlp] Error downloading: {e}")
        return False


def _l1_ytdlp_video(query: str, dest: str, exclude_urls: Optional[set] = None, 
                    max_results: int = 10) -> Optional[Tuple[str, str]]:
    """Search and download CC-licensed video using yt-dlp."""
    if not _check_ytdlp_available():
        print(f"    [yt-dlp] Not available, skipping")
        return None
    
    videos = _search_youtube_cc(query, max_results)
    
    for video in videos:
        video_url = video["url"]
        license_str = video["license"]
        
        if exclude_urls and video_url in exclude_urls:
            continue
            
        print(f"    [yt-dlp] Found CC video: {video['title'][:60]} (license: {license_str})")
        
        if _download_with_ytdlp(video_url, dest):
            return (video_url, license_str or "creativecommons")
    
    return None


def _check_ytdlp_available() -> bool:
    """Check if yt-dlp is installed."""
    try:
        result = subprocess.run(["yt-dlp", "--version"], 
                                capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


if __name__ == "__main__":
    if _check_ytdlp_available():
        print("yt-dlp is available")
    else:
        print("yt-dlp NOT available - install with: pip install yt-dlp")