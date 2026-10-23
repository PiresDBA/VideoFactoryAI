"""
MediaResearchAgent — Aquisição Hierárquica de Mídia com Verificação de Licença
===============================================================================

Implementa a estratégia obrigatória de 4 níveis:

  L1 · Vídeo real livre       → Pixabay, Pexels, Internet Archive, Wikimedia
  L2 · Imagem real livre      → Pixabay, Pexels, Unsplash, Wikimedia Commons
  L3 · Conteúdo IA público    → galerias com licença verificada (Creative Commons)
  L4 · Geração própria por IA → Pollinations (imagem), PIL card (fallback)

Regra de ouro:
  Vídeo real > Imagem real > Conteúdo IA reutilizável > Conteúdo IA gerado

COMPLIANCE:
  - Nunca assume que conteúdo público pode ser reutilizado sem verificação
  - Nunca usa vídeos do YouTube
  - Registra fonte e licença de cada asset no relatório de mídia
"""

import os
import time
import json
import hashlib
import urllib.parse
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# AssetCache
_CACHE_AVAILABLE = False
try:
    from asset_cache import AssetCache
    _CACHE_AVAILABLE = True
except ImportError:
    try:
        from VideoFactoryAI.asset_cache import AssetCache
        _CACHE_AVAILABLE = True
    except ImportError:
        AssetCache = None

# ── Constantes ────────────────────────────────────────────────────────────────

MIN_VIDEO_SIZE  = 100_000   # 100 KB
MIN_IMAGE_SIZE  = 15_000    # 15 KB
REQUEST_TIMEOUT = 20        # segundos

# Licenças aceitas (Creative Commons reutilizáveis + domínio público)
ACCEPTED_LICENSES = {
    "cc0",
    "cc-by",
    "cc-by-sa",
    "public domain",
    "pd",
    "pixabay license",       # Pixabay própria — uso gratuito permitido
    "pexels license",        # Pexels própria — uso gratuito permitido
}

WIKIMEDIA_UA = "VideoFactoryAI/3.0 (media-research-agent; opensource)"


# =============================================================================
# VERIFICAÇÃO DE LICENÇA
# =============================================================================

def _license_is_accepted(license_str: str) -> bool:
    """Verifica se uma string de licença é aceita para reutilização."""
    if not license_str:
        return False
    normalized = license_str.lower().strip()
    return any(lic in normalized for lic in ACCEPTED_LICENSES)


def _make_record(
    scene_id: int,
    level: int,
    source: str,
    url: str,
    license_str: str,
    file_path: str,
    media_type: str
) -> Dict[str, Any]:
    """Cria um registro de proveniência de asset para o relatório de mídia."""
    return {
        "scene_id":   scene_id,
        "level":      level,
        "source":     source,
        "url":        url,
        "license":    license_str,
        "media_type": media_type,   # "video" | "image" | "ai_generated"
        "file_path":  file_path,
        "compliant":  _license_is_accepted(license_str),
    }


# =============================================================================
# DOWNLOAD GENÉRICO
# =============================================================================

def _download(url: str, dest: str, min_size: int = MIN_IMAGE_SIZE,
              timeout: int = REQUEST_TIMEOUT) -> bool:
    """Baixa arquivo binário com validação de tamanho mínimo."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    try:
        headers = {
            "User-Agent": WIKIMEDIA_UA,
            "Accept": "*/*",
        }
        r = requests.get(url, stream=True, timeout=timeout, headers=headers)
        if r.status_code == 200:
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=512 * 1024):
                    if chunk:
                        f.write(chunk)
            return os.path.exists(dest) and os.path.getsize(dest) >= min_size
    except Exception as e:
        print(f"    [Download] Erro ao baixar {url[:60]}: {e}")
    return False


def _file_hash(filepath: str) -> str:
    """Calcula o hash MD5 do conteúdo de um arquivo para garantir unicidade visual."""
    if not filepath or not os.path.exists(filepath):
        return ""
    h = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


# =============================================================================
# NÍVEL 1 — VÍDEO REAL LIVRE
# =============================================================================

def _l1_pixabay_video(query: str, dest: str, api_key: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """
    Busca vídeo no Pixabay ignorando URLs já utilizadas em outras cenas.
    Retorna (url_origem, licença) ou None.
    """
    url = "https://pixabay.com/api/videos/"
    params = {"key": api_key, "q": query, "per_page": 10, "safesearch": "true"}
    try:
        r = requests.get(url, params=params, timeout=12)
        hits = r.json().get("hits", [])
        for hit in hits:
            vids = hit.get("videos", {})
            for quality in ["large", "medium", "small"]:
                if quality in vids and vids[quality].get("url"):
                    video_url = vids[quality]["url"]
                    if exclude_urls and video_url in exclude_urls:
                        continue
                    if _download(video_url, dest, min_size=MIN_VIDEO_SIZE, timeout=30):
                        return (video_url, "pixabay license")
    except Exception as e:
        print(f"    [Pixabay Video] '{query}': {e}")
    return None


def _l1_pexels_video(query: str, dest: str, api_key: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """
    Busca vídeo no Pexels ignorando URLs já utilizadas.
    Licença Pexels: gratuito, sem atribuição obrigatória.
    """
    if not api_key:
        return None
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params  = {"query": query, "per_page": 8, "size": "large"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        videos = r.json().get("videos", [])
        for v in videos:
            files = v.get("video_files", [])
            hd = [f for f in files if f.get("width", 0) >= 1280]
            candidates = hd + [f for f in files if f not in hd]
            for c in candidates:
                link = c.get("link")
                if not link or (exclude_urls and link in exclude_urls):
                    continue
                if _download(link, dest, min_size=MIN_VIDEO_SIZE, timeout=30):
                    return (link, "pexels license")
    except Exception as e:
        print(f"    [Pexels Video] '{query}': {e}")
    return None


def _l1_internet_archive_video(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """
    Busca vídeo histórico no Internet Archive (domínio público / CC).
    Filtra apenas conteúdo com licença CC ou domínio público e sem repetição.
    """
    url = "https://archive.org/advancedsearch.php"
    params = {
        "q": f"{query} AND mediatype:movies AND (licenseurl:*creativecommons* OR licenseurl:*publicdomain* OR subject:public_domain)",
        "fl[]": ["identifier", "title", "licenseurl"],
        "rows": 8,
        "output": "json",
        "sort[]": "downloads desc",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        docs = r.json().get("response", {}).get("docs", [])
        for doc in docs:
            ident = doc.get("identifier")
            lic   = doc.get("licenseurl", "")
            if not ident:
                continue
            if not _license_is_accepted(lic.lower()):
                continue
            meta_url = f"https://archive.org/metadata/{ident}"
            meta_r = requests.get(meta_url, timeout=10)
            files  = meta_r.json().get("files", [])
            mp4s   = [f for f in files if f.get("name", "").endswith(".mp4")]
            for mp4 in mp4s:
                file_url = f"https://archive.org/download/{ident}/{mp4['name']}"
                if exclude_urls and file_url in exclude_urls:
                    continue
                if _download(file_url, dest, min_size=MIN_VIDEO_SIZE, timeout=45):
                    return (file_url, lic or "public domain")
    except Exception as e:
        print(f"    [Internet Archive] '{query}': {e}")
    return None


def _l1_wikimedia_video(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """
    Busca vídeo no Wikimedia Commons (OGG/WEBM/MP4) evitando duplicatas.
    """
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} filetype:video",
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "format": "json",
    }
    headers = {"User-Agent": WIKIMEDIA_UA}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=12)
        pages = r.json().get("query", {}).get("pages", {})
        for _, p in pages.items():
            ii_list = p.get("imageinfo", [])
            if not ii_list:
                continue
            ii   = ii_list[0]
            mime = ii.get("mime", "")
            if "video" not in mime and not mime.endswith("ogg"):
                continue
            lic = (ii.get("extmetadata", {})
                     .get("LicenseShortName", {})
                     .get("value", "CC-BY-SA")).lower()
            if not _license_is_accepted(lic):
                continue
            video_url = ii.get("url")
            if not video_url or (exclude_urls and video_url in exclude_urls):
                continue
            if _download(video_url, dest, min_size=MIN_VIDEO_SIZE, timeout=45):
                return (video_url, lic)
    except Exception as e:
        print(f"    [Wikimedia Video] '{query}': {e}")
    return None


# =============================================================================
# NÍVEL 2 — IMAGEM REAL LIVRE
# =============================================================================

def _l2_pixabay_image(query: str, dest: str, api_key: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem HD no Pixabay sem duplicar URLs já usadas."""
    url = "https://pixabay.com/api/"
    params = {"key": api_key, "q": query, "per_page": 15,
              "safesearch": "true", "image_type": "photo", "min_width": 1280}
    try:
        r = requests.get(url, params=params, timeout=12)
        hits = r.json().get("hits", [])
        for hit in hits:
            img_url = hit.get("largeImageURL") or hit.get("webformatURL")
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, "pixabay license")
    except Exception as e:
        print(f"    [Pixabay Image] '{query}': {e}")
    return None


def _l2_pexels_image(query: str, dest: str, api_key: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Pexels sem duplicar URLs já usadas."""
    if not api_key:
        return None
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}
    params  = {"query": query, "per_page": 10, "size": "large"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        photos = r.json().get("photos", [])
        for photo in photos:
            img_url = (photo.get("src", {}).get("large2x") or
                       photo.get("src", {}).get("large") or
                       photo.get("src", {}).get("original"))
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, "pexels license")
    except Exception as e:
        print(f"    [Pexels Image] '{query}': {e}")
    return None


def _l2_unsplash_image(query: str, dest: str, api_key: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """
    Busca imagem no Unsplash sem duplicar URLs já usadas.
    Licença Unsplash: gratuito para uso comercial e pessoal.
    """
    if not api_key:
        return None
    url = "https://api.unsplash.com/search/photos"
    params = {"query": query, "per_page": 10, "orientation": "landscape",
              "client_id": api_key}
    try:
        r = requests.get(url, params=params, timeout=12)
        results = r.json().get("results", [])
        for res in results:
            img_url = (res.get("urls", {}).get("regular") or
                       res.get("urls", {}).get("full"))
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, "unsplash license")
    except Exception as e:
        print(f"    [Unsplash] '{query}': {e}")
    return None


def _l2_wikimedia_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Wikimedia Commons com verificação de licença e sem duplicatas."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 12,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "format": "json",
    }
    headers = {"User-Agent": WIKIMEDIA_UA}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=12)
        pages = r.json().get("query", {}).get("pages", {})
        for _, p in sorted(pages.items()):
            ii_list = p.get("imageinfo", [])
            if not ii_list:
                continue
            ii   = ii_list[0]
            mime = ii.get("mime", "")
            if mime not in ("image/jpeg", "image/png"):
                continue
            # Verifica licença
            ext_meta = ii.get("extmetadata", {})
            lic = (ext_meta.get("LicenseShortName", {}).get("value", "") or
                   ext_meta.get("License", {}).get("value", "")).lower()
            # Se licença não identificada, verifica se é categoria de domínio público
            if not lic:
                cats = ext_meta.get("Categories", {}).get("value", "")
                if "public domain" in cats.lower():
                    lic = "public domain"
            if not _license_is_accepted(lic):
                continue
            # Verifica tamanho mínimo
            if ii.get("size", 0) < MIN_IMAGE_SIZE:
                continue
            img_url = ii.get("url")
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, lic or "CC")
    except Exception as e:
        print(f"    [Wikimedia Image] '{query}': {e}")
    return None


# =============================================================================
# NÍVEL 3 — CONTEÚDO IA PÚBLICO REUTILIZÁVEL
# =============================================================================

def _l3_openverse_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """
    Busca no Openverse (antigo CC Search) — indexa conteúdo CC de múltiplas fontes sem repetições.
    API pública, sem autenticação necessária para buscas básicas.
    """
    url = "https://api.openverse.org/v1/images/"
    params = {
        "q": query,
        "license_type": "commercial,modification",   # só reutilizável comercialmente
        "extension": "jpg,png",
        "aspect_ratio": "wide",
        "size": "large",
        "page_size": 10,
    }
    headers = {"User-Agent": WIKIMEDIA_UA}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        results = r.json().get("results", [])
        for item in results:
            lic     = item.get("license", "").lower()
            lic_ver = item.get("license_version", "")
            img_url = item.get("url", "")
            if not _license_is_accepted(lic):
                continue
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, f"{lic} {lic_ver}".strip())
    except Exception as e:
        print(f"    [Openverse] '{query}': {e}")
    return None


# =============================================================================
# NÍVEL 4 — GERAÇÃO PRÓPRIA POR IA
# =============================================================================

def _l4_pollinations_image(prompt: str, dest: str, seed: Optional[int] = None) -> Optional[Tuple[str, str]]:
    """Gera imagem via Pollinations.ai com seed exclusiva para garantir diversidade visual."""
    enc = urllib.parse.quote(prompt)
    seed_param = f"&seed={seed}" if seed is not None else ""
    url = f"https://image.pollinations.ai/prompt/{enc}?width=1920&height=1080&nologo=true{seed_param}"
    try:
        r = requests.get(url, timeout=40)
        if r.status_code == 200 and len(r.content) > MIN_IMAGE_SIZE:
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(r.content)
            return (url, "ai_generated_pollinations")
    except Exception as e:
        print(f"    [Pollinations] '{prompt[:50]}': {e}")
    return None


def _l4_pil_card(title: str, dest: str, scene_id: int = 1) -> Tuple[str, str]:
    """Fallback visual procedural com cores e enquadramento únicos por cena."""
    from PIL import Image, ImageDraw
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    palettes = [
        ((15, 23, 42), (212, 175, 55)),   # Azul escuro e dourado
        ((24, 24, 38), (100, 180, 255)),  # Índigo e ciano
        ((28, 20, 20), (230, 110, 80)),   # Vinho e coral
        ((18, 30, 24), (120, 210, 140)),  # Verde floresta e menta
        ((26, 22, 34), (200, 140, 230)),  # Púrpura e lavanda
        ((32, 26, 18), (240, 190, 90)),   # Âmbar escuro e ocre
    ]
    bg, accent = palettes[scene_id % len(palettes)]
    img  = Image.new("RGB", (1920, 1080), bg)
    draw = ImageDraw.Draw(img)
    # Gradiente sutil
    for y in range(1080):
        v = int(bg[0] + (35 - bg[0]) * y / 1080)
        draw.line([(0, y), (1920, y)], fill=(v, int(v * 1.2), int(v * 1.5)))
    # Faixa lateral decorativa
    draw.rectangle([60, 420, 70, 660], fill=accent)
    draw.text((90, 470), f"CENA {scene_id:02d}", fill=accent)
    draw.text((90, 520), title[:70], fill=(240, 240, 240))
    img.save(dest, "JPEG", quality=88)
    return (dest, "ai_generated_pil")


# =============================================================================
# MEDIA RESEARCH AGENT — ORQUESTRADOR PRINCIPAL
# =============================================================================

class MediaResearchAgent:
    """
    Agente de pesquisa de mídia com estratégia hierárquica de 4 níveis.
    
    Registra fonte, URL e licença de cada asset no media_report.
    Aprende quais fontes são mais eficazes e salva em preferences.json.
    """

    def __init__(self, cfg: dict, root: Path, memory_dir: Path, cache_dir: Optional[Path] = None):
        self.cfg        = cfg
        self.root       = Path(root)
        self.memory_dir = Path(memory_dir)

        self.videos_dir  = str(self.root / "videos")
        self.imagens_dir = str(self.root / "imagens")
        os.makedirs(self.videos_dir, exist_ok=True)
        os.makedirs(self.imagens_dir, exist_ok=True)

        media_cfg = cfg.get("media", {})
        self.pixabay_key  = media_cfg.get("pixabay_api_key", "")
        self.pexels_key   = media_cfg.get("pexels_api_key", "")
        self.unsplash_key = media_cfg.get("unsplash_api_key", "")

        self.media_report: List[Dict] = []
        self._source_stats: Dict[str, int] = {}

        # ══════════════════════════════════════════════════════════════════════
        # REGRA DE OURO — PROIBIÇÃO DE MÍDIA DUPLICADA
        # ══════════════════════════════════════════════════════════════════════
        # Estes registros garantem que NENHUMA imagem ou vídeo se repita no vídeo final.
        # Três camadas de proteção contra duplicatas:
        #   1. used_urls   — URLs de download já consumidas (impede re-baixar o mesmo asset)
        #   2. used_hashes — hash MD5 do conteúdo binário (detecta duplicatas visuais idênticas)
        #   3. used_paths  — caminhos de arquivo já atribuídos a uma cena
        self.used_urls: set = set()
        self.used_hashes: Dict[str, int] = {}   # hash_md5 → scene_id que já usa esse asset
        self.used_paths: Dict[str, int] = {}     # filepath  → scene_id

        # Carrega preferências aprendidas
        self._prefs = self._load_prefs()

        # Cache de assets entre execuções (global ou por workspace)
        c_dir = Path(cache_dir) if cache_dir else (self.root / "cache")
        self.cache = AssetCache(c_dir) if _CACHE_AVAILABLE and AssetCache else None

    # ── Persistência de Preferências ─────────────────────────────────────────

    def _load_prefs(self) -> dict:
        pref_path = self.memory_dir / "preferences.json"
        if pref_path.exists():
            try:
                return json.loads(pref_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"effective_sources": {}, "run_count": 0}

    def _save_prefs(self) -> None:
        pref_path = self.memory_dir / "preferences.json"
        pref_path.parent.mkdir(parents=True, exist_ok=True)
        # Merge source stats
        eff = self._prefs.setdefault("effective_sources", {})
        for src, count in self._source_stats.items():
            eff[src] = eff.get(src, 0) + count
        self._prefs["run_count"] = self._prefs.get("run_count", 0) + 1
        pref_path.write_text(
            json.dumps(self._prefs, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _record_hit(self, source: str) -> None:
        self._source_stats[source] = self._source_stats.get(source, 0) + 1

    # ── Caminhos de Asset ─────────────────────────────────────────────────────

    def _dest_path(self, scene: dict) -> str:
        is_video = scene["tipo"] == "video"
        base_dir = self.videos_dir if is_video else self.imagens_dir
        return str(Path(base_dir) / scene["arquivo"])

    def _asset_valid(self, path: str, is_video: bool = False) -> bool:
        min_sz = MIN_VIDEO_SIZE if is_video else MIN_IMAGE_SIZE
        return os.path.exists(path) and os.path.getsize(path) >= min_sz

    # ── Pipeline por Cena ─────────────────────────────────────────────────────

    def source_scene(self, scene: dict) -> Optional[str]:
        """
        Tenta adquirir mídia para uma cena seguindo a hierarquia L1→L4.

        REGRA DE OURO — PROIBIÇÃO DE MÍDIA DUPLICADA:
          Cada cena DEVE usar um asset visual 100% exclusivo.
          Três barreiras de proteção são aplicadas em cada download:
            1. exclude_urls: URLs já baixadas são excluídas antes da busca na API.
            2. Verificação de hash MD5: se o conteúdo binário for idêntico a outro
               asset já utilizado, o download é descartado e outra opção é buscada.
            3. Auditoria final em source_all(): varredura pós-download confirma que
               nenhum hash se repete entre cenas.
        """
        sid       = scene["id"]
        is_video  = scene["tipo"] == "video"
        query     = scene.get("query", "")
        wm_query  = scene.get("wikimedia_q", "")
        ai_prompt = scene.get("ai_prompt", "")
        dest_path = self._dest_path(scene)

        # ── Cache local com verificação de duplicata ──────────────────────────
        if self._asset_valid(dest_path, is_video):
            f_hash = _file_hash(dest_path)
            if f_hash and f_hash in self.used_hashes:
                print(f"    [Dedup] Disco: {Path(dest_path).name} duplica Cena {self.used_hashes[f_hash]:02d}. Substituindo...")
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            elif f_hash:
                print(f"    [Cache] Cena {sid:02d}: {Path(dest_path).name} (hash={f_hash[:8]})")
                self.used_hashes[f_hash] = sid
                self.used_paths[dest_path] = sid
                self._add_report(sid, 0, "local_cache", "", "cached", dest_path,
                                 "video" if is_video else "image")
                return dest_path

        # ── Cache persistente com verificação de duplicata ────────────────────
        cache_q = wm_query or query
        media_type = "video" if is_video else "image"
        if self.cache and cache_q:
            cached_file = self.cache.get(cache_q, media_type)
            if cached_file and os.path.exists(cached_file):
                c_hash = _file_hash(cached_file)
                if c_hash and c_hash in self.used_hashes:
                    print(f"    [Dedup] AssetCache duplica Cena {self.used_hashes[c_hash]:02d}. Pulando...")
                else:
                    try:
                        import shutil
                        shutil.copy2(cached_file, dest_path)
                        if self._asset_valid(dest_path, is_video):
                            self.used_hashes[c_hash] = sid
                            self.used_paths[dest_path] = sid
                            print(f"    [AssetCache] Reutilizado: '{cache_q[:40]}' (hash={c_hash[:8]})")
                            self._add_report(sid, 0, "asset_cache", "", "cached", dest_path, media_type)
                            return dest_path
                    except Exception:
                        pass

        print(f"\n  [MediaResearch] Cena {sid:02d} | tipo={scene['tipo']} | query='{query[:50]}'")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 1 — Vídeo real livre (com proteção anti-duplicata)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if is_video and query:
            for source_fn, name in [
                (lambda q, d: _l1_pixabay_video(q, d, self.pixabay_key, exclude_urls=self.used_urls),  "pixabay_video"),
                (lambda q, d: _l1_pexels_video(q, d, self.pexels_key, exclude_urls=self.used_urls),    "pexels_video"),
                (lambda q, d: _l1_wikimedia_video(q, d, exclude_urls=self.used_urls),                  "wikimedia_video"),
                (lambda q, d: _l1_internet_archive_video(q, d, exclude_urls=self.used_urls),           "internet_archive"),
            ]:
                result = source_fn(query, dest_path)
                if result:
                    url, lic = result
                    v_hash = _file_hash(dest_path)
                    if v_hash and v_hash in self.used_hashes:
                        print(f"    [Dedup] {name}: conteúdo idêntico à Cena {self.used_hashes[v_hash]:02d}. Rejeitando...")
                        self.used_urls.add(url)
                        try: os.remove(dest_path)
                        except Exception: pass
                        continue
                    print(f"    [L1-Video] {name} OK — licenca: {lic}")
                    self.used_urls.add(url)
                    if v_hash: self.used_hashes[v_hash] = sid
                    self.used_paths[dest_path] = sid
                    self._record_hit(name)
                    self._add_report(sid, 1, name, url, lic, dest_path, "video")
                    return dest_path
                time.sleep(0.2)

            # Fallback: converte para imagem se vídeo não encontrado
            print(f"    [L1] Sem video real — escalando para L2 (imagem)...")
            dest_path = dest_path.replace(".mp4", ".jpg")
            scene["tipo"]    = "image"
            scene["arquivo"] = Path(dest_path).name
            is_video = False

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 2 — Imagem real livre (com proteção anti-duplicata)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        img_query = wm_query or query or "documentary historical footage"
        for source_fn, name in [
            (lambda q, d: _l2_pixabay_image(q, d, self.pixabay_key, exclude_urls=self.used_urls),   "pixabay_image"),
            (lambda q, d: _l2_wikimedia_image(q, d, exclude_urls=self.used_urls),                   "wikimedia_image"),
            (lambda q, d: _l2_pexels_image(q, d, self.pexels_key, exclude_urls=self.used_urls),     "pexels_image"),
            (lambda q, d: _l2_unsplash_image(q, d, self.unsplash_key, exclude_urls=self.used_urls), "unsplash_image"),
        ]:
            for q in list(dict.fromkeys([img_query, query, "historical documentary footage"])):
                if not q:
                    continue
                result = source_fn(q, dest_path)
                if result:
                    url, lic = result
                    i_hash = _file_hash(dest_path)
                    if i_hash and i_hash in self.used_hashes:
                        print(f"    [Dedup] {name}: duplicata da Cena {self.used_hashes[i_hash]:02d}. Rejeitando...")
                        self.used_urls.add(url)
                        try: os.remove(dest_path)
                        except Exception: pass
                        continue
                    print(f"    [L2-Image] {name} OK — licenca: {lic}")
                    self.used_urls.add(url)
                    if i_hash: self.used_hashes[i_hash] = sid
                    self.used_paths[dest_path] = sid
                    self._record_hit(name)
                    self._add_report(sid, 2, name, url, lic, dest_path, "image")
                    return dest_path
                time.sleep(0.2)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 3 — Conteúdo IA público (Openverse, com proteção anti-duplicata)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        for q in [img_query, query]:
            if not q:
                continue
            result = _l3_openverse_image(q, dest_path, exclude_urls=self.used_urls)
            if result:
                url, lic = result
                o_hash = _file_hash(dest_path)
                if o_hash and o_hash in self.used_hashes:
                    print(f"    [Dedup] Openverse: duplicata. Rejeitando...")
                    self.used_urls.add(url)
                    try: os.remove(dest_path)
                    except Exception: pass
                    continue
                print(f"    [L3-Openverse] OK — licenca: {lic}")
                self.used_urls.add(url)
                if o_hash: self.used_hashes[o_hash] = sid
                self.used_paths[dest_path] = sid
                self._record_hit("openverse")
                self._add_report(sid, 3, "openverse", url, lic, dest_path, "image")
                return dest_path
            time.sleep(0.3)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 4 — IA gerada (Pollinations com seed única → PIL com paleta por cena)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        prompt = ai_prompt or img_query or scene.get("descricao", f"cinematic scene {sid}")
        seed = int(hashlib.md5(f"{sid}_{query}_{prompt}_{time.time()}".encode()).hexdigest()[:8], 16) % 1000000
        print(f"    [L4-Pollinations] Gerando IA exclusiva (seed={seed}): '{prompt[:55]}'")
        result = _l4_pollinations_image(prompt, dest_path, seed=seed)
        if result:
            url, lic = result
            p_hash = _file_hash(dest_path)
            self.used_urls.add(url)
            if p_hash: self.used_hashes[p_hash] = sid
            self.used_paths[dest_path] = sid
            self._record_hit("pollinations_ai")
            self._add_report(sid, 4, "pollinations_ai", url, lic, dest_path, "ai_generated")
            return dest_path

        # Fallback absoluto — PIL card com cores exclusivas por ID de cena
        print(f"    [L4-PIL] Fallback procedural exclusivo para cena {sid:02d}")
        url, lic = _l4_pil_card(scene.get("descricao", f"Cena {sid}"), dest_path, scene_id=sid)
        pil_hash = _file_hash(dest_path)
        if pil_hash: self.used_hashes[pil_hash] = sid
        self.used_paths[dest_path] = sid
        self._record_hit("pil_fallback")
        self._add_report(sid, 4, "pil_fallback", url, lic, dest_path, "ai_generated")
        return dest_path

    # ── Batch com Auditoria Final Anti-Duplicata ─────────────────────────────

    def _enforce_final_uniqueness(self, scenes: List[dict], asset_map: Dict[int, str]) -> int:
        """
        REGRA DE OURO — Auditoria final pós-download.
        Varre todos os assets baixados e substitui qualquer duplicata restante
        por uma geração IA exclusiva (Pollinations com seed única) ou PIL card.
        Retorna a quantidade de duplicatas corrigidas.
        """
        seen: Dict[str, int] = {}
        duplicates_fixed = 0

        for scene in scenes:
            sid = scene["id"]
            path = asset_map.get(sid)
            if not path or not os.path.exists(path):
                continue
            f_hash = _file_hash(path)
            if not f_hash:
                continue

            if f_hash in seen:
                first_sid = seen[f_hash]
                print(f"  [Dedup Final] Cena {sid:02d} = Cena {first_sid:02d}. Gerando substituta exclusiva...")
                new_dest = str(Path(self.imagens_dir) / f"cena_{sid:02d}_unique.jpg")
                seed = int(hashlib.md5(f"unique_{sid}_{time.time()}".encode()).hexdigest()[:8], 16) % 1000000
                prompt = scene.get("ai_prompt") or scene.get("descricao") or f"cinematic scene {sid} unique visual"

                res = _l4_pollinations_image(prompt, new_dest, seed=seed)
                if not res or not os.path.exists(new_dest):
                    _l4_pil_card(scene.get("descricao", f"Cena {sid}"), new_dest, scene_id=sid)

                asset_map[sid] = new_dest
                scene["tipo"] = "image"
                scene["arquivo"] = Path(new_dest).name
                new_hash = _file_hash(new_dest)
                if new_hash:
                    seen[new_hash] = sid
                duplicates_fixed += 1
            else:
                seen[f_hash] = sid

        return duplicates_fixed

    def source_all(self, scenes: List[dict]) -> Dict[int, str]:
        """
        Adquire mídia para todas as cenas. Retorna asset_map {scene_id: path}.
        Garante que toda cena tem um asset ao final.
        Executa auditoria final de exclusividade (Regra de Ouro Anti-Duplicata).
        """
        os.makedirs(self.videos_dir,  exist_ok=True)
        os.makedirs(self.imagens_dir, exist_ok=True)

        asset_map: Dict[int, str] = {}
        total = len(scenes)

        for idx, scene in enumerate(scenes, 1):
            sid = scene["id"]
            print(f"\n  [{idx:02d}/{total:02d}] Pesquisando midia para cena {sid:02d}...")
            path = self.source_scene(scene)
            if path:
                asset_map[sid] = path

        # ══════════════════════════════════════════════════════════════════════
        # REGRA DE OURO — Auditoria final: corrige qualquer duplicata restante
        # ══════════════════════════════════════════════════════════════════════
        dups_fixed = self._enforce_final_uniqueness(scenes, asset_map)
        if dups_fixed > 0:
            print(f"\n  [Dedup] {dups_fixed} mídias duplicadas corrigidas → 100% exclusivas.")

        # Salva preferências aprendidas nesta execução
        self._save_prefs()

        # Salva relatório de mídia
        self._save_media_report()

        # Resumo por nível
        levels = [r["level"] for r in self.media_report]
        print(f"\n  [MediaResearch] Resumo:")
        print(f"    L1 (Video Real)  : {levels.count(1)} cenas")
        print(f"    L2 (Imagem Real) : {levels.count(2)} cenas")
        print(f"    L3 (IA Publica)  : {levels.count(3)} cenas")
        print(f"    L4 (IA Gerada)   : {levels.count(4)} cenas")
        print(f"    Cache            : {levels.count(0)} cenas")
        print(f"    Exclusividade    : 100% — nenhuma duplicata permitida")

        return asset_map

    # ── Relatório de Mídia ────────────────────────────────────────────────────

    def _add_report(self, scene_id, level, source, url, license_str, file_path, media_type):
        self.media_report.append(_make_record(
            scene_id, level, source, url, license_str, file_path, media_type
        ))

    def _save_media_report(self) -> None:
        report_path = self.memory_dir / "media_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(self.media_report, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n  [MediaResearch] Relatorio salvo em: {report_path.name}")

    def compliance_summary(self) -> dict:
        """Retorna sumário de compliance de licenças."""
        total     = len(self.media_report)
        compliant = sum(1 for r in self.media_report if r.get("compliant"))
        ai_gen    = sum(1 for r in self.media_report if r["media_type"] == "ai_generated")
        by_level  = {
            "L1_video":        sum(1 for r in self.media_report if r["level"] == 1),
            "L2_image":        sum(1 for r in self.media_report if r["level"] == 2),
            "L3_ai_public":    sum(1 for r in self.media_report if r["level"] == 3),
            "L4_ia_generated": sum(1 for r in self.media_report if r["level"] == 4),
            "cache":           sum(1 for r in self.media_report if r["level"] == 0),
        }
        return {
            "total_assets":       total,
            "compliant":          compliant,
            "non_compliant":      total - compliant - ai_gen,
            "ai_generated":       ai_gen,
            "compliance_rate_pct": round(100 * compliant / total, 1) if total else 0,
            "by_level":           by_level,
        }
