# -*- coding: utf-8 -*-
"""YouTube CC video search/download helper for VideoFactoryAI.

Only accepts an explicit Creative Commons/public-domain license reported by
full yt-dlp video metadata. Search text/description alone is not proof of license.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List, Dict

_check_ytdlp_available_cache = [None]


def _youtube_runtime_args() -> List[str]:
    """Enable current YouTube JS challenge support when Node is present."""
    args: List[str] = []
    if shutil.which("node"):
        args.extend(["--js-runtimes", "node"])
    if not importlib.util.find_spec("yt_dlp_ejs"):
        # Official yt-dlp EJS scripts are fetched on demand by yt-dlp.
        args.extend(["--remote-components", "ejs:github"])
    return args


def _ytdlp_base_cmd() -> List[str]:
    """Prefer the current Python environment; supports installs without a PATH shim."""
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        exe = shutil.which("yt-dlp") or shutil.which("yt_dlp")
        return [exe] if exe else [sys.executable, "-m", "yt_dlp"]


def _check_ytdlp_available() -> bool:
    if _check_ytdlp_available_cache[0] is not None:
        return bool(_check_ytdlp_available_cache[0])
    try:
        r = subprocess.run(_ytdlp_base_cmd() + ["--version"], capture_output=True,
                          text=True, timeout=10, check=False)
        ok = r.returncode == 0
        if not ok:
            detail = (r.stderr or r.stdout or "sem detalhes").strip().splitlines()
            print(f"    [yt-dlp] Não disponível: {detail[-1][:240] if detail else 'erro desconhecido'}")
    except Exception as exc:
        ok = False
        print(f"    [yt-dlp] Falha ao verificar instalação: {exc}")
    _check_ytdlp_available_cache[0] = ok
    return ok


def _normalize_license(value: object) -> str:
    return str(value or "").strip().lower()


def _is_cc_licensed(license_str: str, description: str = "") -> bool:
    """Strict: accept explicit metadata license only, not description keywords."""
    lic = _normalize_license(license_str)
    if not lic:
        return False
    denied = ("noncommercial", "non-commercial", "cc-by-nc", "cc by-nc",
              "no derivatives", "no-derivatives", "standard youtube license",
              "all rights reserved")
    if any(term in lic for term in denied):
        return False
    accepted = ("creative commons", "creativecommons", "cc-by", "cc by", "cc0",
                "public domain", "publicdomain", "public domain mark")
    return any(term in lic for term in accepted)


def _extract_license_from_yt_metadata(info: dict) -> str:
    """Read actual license fields from full yt-dlp metadata; don't infer from tags."""
    for key in ("license", "license_name", "license_id", "license_url"):
        val = info.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _metadata_matches_query(query: str, info: dict) -> bool:
    """Use returned title/description as a cheap relevance gate before download."""
    query_text = str(query or "").lower()
    metadata = " ".join(str(info.get(key, "") or "") for key in ("title", "description", "channel", "uploader")).lower()
    if not metadata.strip():
        return False
    rail_context = any(term in query_text for term in ("model railroad", "model railway", "ho scale", "benchwork"))
    if rail_context:
        miniature = any(term in metadata for term in (
            "model railroad", "model railway", "model train", "model trains",
            "ho scale", "n scale", "scale model", "miniature train",
        ))
        rail_subject = any(term in metadata for term in (
            "railroad", "railway", "train", "locomotive", "track", "benchwork", "l-girder",
        ))
        return miniature and rail_subject
    stop = {"cinematic", "documentary", "footage", "close", "wide", "shot", "detail",
            "macro", "lighting", "realistic", "video", "the", "with", "from", "and", "for"}
    terms = [word for word in query_text.split() if len(word) >= 4 and word not in stop]
    return not terms or any(term in metadata for term in terms)


def _search_youtube_cc(query: str, max_results: int = 10) -> List[Dict]:
    """Search YouTube once for full metadata, accepting explicit reusable licenses only."""
    if not _check_ytdlp_available():
        return []
    if not shutil.which("node") and not shutil.which("deno"):
        print("    [yt-dlp] Sem runtime JavaScript (Node/Deno); a busca no YouTube pode retornar poucos resultados.")
    count = max(1, min(int(max_results), 30))
    cmd = _ytdlp_base_cmd() + _youtube_runtime_args() + [
        f"ytsearch{count}:{query}", "--skip-download",
        "--dump-json", "--no-warnings", "--ignore-errors",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
        if result.returncode not in (0, 1):
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            print(f"    [yt-dlp] Busca falhou (código {result.returncode}): {detail[-1][:240] if detail else 'sem detalhes'}")
        videos = []
        candidates_seen = 0
        metadata_failures = 0
        license_rejections = 0
        relevance_rejections = 0
        for line in (result.stdout or "").splitlines():
            try:
                metadata = json.loads(line)
            except json.JSONDecodeError:
                metadata_failures += 1
                continue
            vid = metadata.get("id")
            url = metadata.get("webpage_url") or (f"https://www.youtube.com/watch?v={vid}" if vid else None)
            if not vid or not url:
                metadata_failures += 1
                continue
            candidates_seen += 1
            if not _metadata_matches_query(query, metadata):
                relevance_rejections += 1
                continue
            license_str = _extract_license_from_yt_metadata(metadata)
            if not _is_cc_licensed(license_str):
                license_rejections += 1
                continue
            videos.append({"id": vid, "title": metadata.get("title") or "(sem título)",
                           "url": url, "duration": metadata.get("duration"),
                           "license": license_str, "uploader": metadata.get("uploader"),
                           "view_count": metadata.get("view_count")})
        print(
            f"    [yt-dlp] Busca '{query[:70]}': {candidates_seen} candidatos com metadados completos; "
            f"{len(videos)} relevantes e com licença explícita aceita; {relevance_rejections} fora do assunto; "
            f"{metadata_failures} sem metadados acessíveis; "
            f"{license_rejections} sem licença comercial reutilizável explícita."
        )
        return videos
    except subprocess.TimeoutExpired:
        print(f"    [yt-dlp] Timeout pesquisando '{query[:100]}'")
    except Exception as exc:
        print(f"    [yt-dlp] Erro na busca: {exc}")
    return []


def _download_with_ytdlp(video_url: str, dest: str, format_selector: str = None) -> bool:
    """Download to a temporary template, then move the actual media file to dest."""
    if not _check_ytdlp_available():
        return False
    destination = Path(dest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if format_selector is None:
        format_selector = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best"
    temp_dir = Path(tempfile.mkdtemp(prefix="vf_ytdlp_", dir=str(destination.parent)))
    template = str(temp_dir / "download.%(ext)s")
    cmd = _ytdlp_base_cmd() + _youtube_runtime_args() + ["--no-warnings", "--no-playlist", "--no-part",
        "--retries", "2", "--fragment-retries", "2", "-f", format_selector,
        "-o", template, video_url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=240, check=False)
        files = [x for x in temp_dir.iterdir() if x.is_file() and x.stat().st_size > 100_000]
        # Prefer a final merged media file, ignoring subtitle/thumbnail sidecars.
        media = [x for x in files if x.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4v")]
        if result.returncode != 0 or not media:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            print(f"    [yt-dlp] Download falhou para {video_url}: {detail[-1][:260] if detail else 'nenhum arquivo de vídeo produzido'}")
            return False
        chosen = max(media, key=lambda x: x.stat().st_size)
        shutil.move(str(chosen), str(destination))
        ok = destination.is_file() and destination.stat().st_size > 100_000
        if not ok:
            try: destination.unlink(missing_ok=True)
            except OSError: pass
        return ok
    except subprocess.TimeoutExpired:
        print(f"    [yt-dlp] Timeout baixando '{video_url}'")
    except Exception as exc:
        print(f"    [yt-dlp] Erro no download: {exc}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return False


def _l1_ytdlp_video(query: str, dest: str, exclude_urls: Optional[set] = None,
                    max_results: int = 10) -> Optional[Tuple[str, str]]:
    """Search and download a video with explicit reusable CC/public-domain metadata."""
    videos = _search_youtube_cc(query, max_results)
    for video in videos:
        url = video["url"]
        if exclude_urls and url in exclude_urls:
            continue
        print(f"    [yt-dlp] Candidato CC: {video['title'][:70]} (licença declarada: {video['license']})")
        if _download_with_ytdlp(url, dest):
            return url, video["license"]
    return None


if __name__ == "__main__":
    print("yt-dlp disponível" if _check_ytdlp_available() else "yt-dlp NÃO disponível; instale no Python do projeto: python -m pip install -U yt-dlp")
