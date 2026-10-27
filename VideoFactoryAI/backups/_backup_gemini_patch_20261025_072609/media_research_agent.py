"""
MediaResearchAgent — Aquisição Hierárquica de Mídia com Verificação de Licença
===============================================================================

Implementa a estratégia obrigatória de 4 níveis:

  L1 · Vídeo real livre       → Pixabay, Pexels, Internet Archive, Wikimedia
                                YouTube opcional e secundário: CC ou arquivo local autorizado; provedores existentes têm prioridade
  L2 · Imagem real livre      → Pixabay, Pexels, Unsplash, Wikimedia Commons
  L3 · Conteúdo IA público    → galerias com licença verificada (Creative Commons)
  L4 · Geração própria por IA → Pollinations (imagem), PIL card (fallback)

Regra de ouro:
  Vídeo real > Imagem real > Conteúdo IA reutilizável > Conteúdo IA gerado

COMPLIANCE:
  - Nunca assume que conteúdo público pode ser reutilizado sem verificação
  - YouTube é opt-in por execução via --youtube-mode (off/cc/authorized/both) e nunca precede Pixabay/Pexels/Wikimedia/Internet Archive
  - O modo authorized recebe arquivo LOCAL; não baixa vídeos por URL
  - Registra fonte, licença/base declarada e proveniência de cada asset
  - Metadados de licença encontrados automaticamente são indícios, não garantia jurídica
"""

import os
import re
import time
import json
import subprocess
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

# yt-dlp downloader for CC-licensed videos
_YTDLP_AVAILABLE = False
try:
    from ytdlp_downloader import _l1_ytdlp_video, _check_ytdlp_available
    _YTDLP_AVAILABLE = True
except ImportError:
    _l1_ytdlp_video = None
    _check_ytdlp_available = None
    _YTDLP_AVAILABLE = False

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
# NÍVEL 1 — NOVAS FONTES DE VÍDEO LIVRE (20 sites gratuitos)
# =============================================================================

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
# NÍVEL 2 — NOVAS FONTES DE IMAGEM LIVRE (36 sites gratuitos)
# =============================================================================

# Mapeamento de sites para funções de busca HTML
FREE_IMAGE_SOURCES = {
    "burst": {
        "url": "https://burst.shopify.com/photos/search",
        "params": {"term": "{query}"},
        "license": "burst license",
    },
    "unsplash": {
        "url": "https://unsplash.com/s/photos/{query}",
        "params": {},
        "license": "unsplash license",
    },
    "pexels": {
        "url": "https://www.pexels.com/search/{query}/",
        "params": {},
        "license": "pexels license",
    },
    "shutterstock": {
        "url": "https://www.shutterstock.com/search/{query}",
        "params": {"license": "rf"},
        "license": "shutterstock license",
    },
    "gettyimages": {
        "url": "https://www.gettyimages.com/search/2/image?phrase={query}",
        "params": {},
        "license": "gettyimages license",
    },
    "canva": {
        "url": "https://www.canva.com/photos/search/{query}/",
        "params": {},
        "license": "canva license",
    },
    "istock": {
        "url": "https://www.istockphoto.com/search/2/image?phrase={query}",
        "params": {},
        "license": "istock license",
    },
    "freepik": {
        "url": "https://www.freepik.com/search?format=search&query={query}",
        "params": {},
        "license": "freepik license",
    },
    "picjumbo": {
        "url": "https://picjumbo.com/search/{query}/",
        "params": {},
        "license": "picjumbo license",
    },
    "lifeofpix": {
        "url": "https://www.lifeofpix.com/search/?q={query}",
        "params": {},
        "license": "lifeofpix license",
    },
    "depositphotos": {
        "url": "https://depositphotos.com/stock-photos/{query}.html",
        "params": {},
        "license": "depositphotos license",
    },
    "isorepublic": {
        "url": "https://isorepublic.com/search/?s={query}",
        "params": {},
        "license": "isorepublic license",
    },
    "freeimages": {
        "url": "https://www.freeimages.com/search/{query}",
        "params": {},
        "license": "freeimages license",
    },
    "gratispics": {
        "url": "https://gratispics.com/search/{query}/",
        "params": {},
        "license": "gratispics license",
    },
    "newoldstock": {
        "url": "https://nos.twnsnd.co/search?q={query}",
        "params": {},
        "license": "newoldstock license",
    },
    "kaboompics": {
        "url": "https://kaboompics.com/search?q={query}",
        "params": {},
        "license": "kaboompics license",
    },
    "freerange": {
        "url": "https://freerangestock.com/search.php?search={query}",
        "params": {},
        "license": "freerange license",
    },
    "adobestock": {
        "url": "https://stock.adobe.com/search?k={query}",
        "params": {},
        "license": "adobestock license",
    },
    "stocksnap": {
        "url": "https://stocksnap.io/search/{query}",
        "params": {},
        "license": "stocksnap license",
    },
    "stockvault": {
        "url": "https://www.stockvault.net/search/{query}",
        "params": {},
        "license": "stockvault license",
    },
    "foodiesfeed": {
        "url": "https://www.foodiesfeed.com/search/?q={query}",
        "params": {},
        "license": "foodiesfeed license",
    },
    "focastock": {
        "url": "https://focastock.com/search/{query}/",
        "params": {},
        "license": "focastock license",
    },
    "morguefile": {
        "url": "https://morguefile.com/search/{query}",
        "params": {},
        "license": "morguefile license",
    },
    "pikwizard": {
        "url": "https://www.pikwizard.com/search?q={query}",
        "params": {},
        "license": "pikwizard license",
    },
    "reshot": {
        "url": "https://www.reshot.com/search/?q={query}",
        "params": {},
        "license": "reshot license",
    },
    "freestocks": {
        "url": "https://freestocks.org/search/{query}",
        "params": {},
        "license": "freestocks license",
    },
    "picography": {
        "url": "https://picography.co/search/?s={query}",
        "params": {},
        "license": "picography license",
    },
    "skitterphoto": {
        "url": "https://skitterphoto.com/search?q={query}",
        "params": {},
        "license": "skitterphoto license",
    },
    "littlevisuals": {
        "url": "https://littlevisuals.co/search/?s={query}",
        "params": {},
        "license": "littlevisuals license",
    },
    "jaymantri": {
        "url": "https://jaymantri.com/search/?s={query}",
        "params": {},
        "license": "jaymantri license",
    },
    "picspree": {
        "url": "https://picspree.com/search?q={query}",
        "params": {},
        "license": "picspree license",
    },
    "libreshot": {
        "url": "https://libreshot.com/search/?s={query}",
        "params": {},
        "license": "libreshot license",
    },
    "startupstockphotos": {
        "url": "https://startupstockphotos.com/search/?s={query}",
        "params": {},
        "license": "startupstockphotos license",
    },
    "rgbstock": {
        "url": "https://www.rgbstock.com/search/{query}",
        "params": {},
        "license": "rgbstock license",
    },
    "negativespace": {
        "url": "https://negativespace.co/search/{query}",
        "params": {},
        "license": "negativespace license",
    },
}


_IMG_EXT = r"(?:jpg|jpeg|png|webp)"

# Termos que indicam logo, ícone, banner ou placeholder — nunca servem como cena.
_IMG_LIXO = (
    "logo", "icon", "avatar", "sprite", "placeholder", "favicon", "badge",
    "blank", "spacer", "emoji", "pixel.gif", "1x1", "loading", "spinner",
    "flag-", "/flags/", "watermark", "noimage", "no-image", "default.",
    "advert", "banner", "promo", "gravatar", "data:image",
    # cartões sociais / opengraph não são conteúdo da cena
    "/og/", "og-image", "og_image", "opengraph", "social", "share-image",
    "twitter-card", "twittercard", "preview-image", "/thumb/", "thumbnail",
)


def _extrair_candidatos_imagem(html: str, base_url: str) -> List[str]:
    """
    Extrai URLs de imagem prováveis de uma página HTML, priorizando as maiores.

    Estratégia:
      1. og:image (normalmente a imagem principal em alta)
      2. srcset — escolhe a maior variante de cada conjunto
      3. src / data-src / data-lazy-src / data-original
      4. background-image em CSS inline
    Descarta logos, ícones, avatares e placeholders.
    """
    from urllib.parse import urljoin

    cands: List[str] = []
    og_cands: List[str] = []

    for m in re.findall(
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.I
    ):
        og_cands.append(m)

    for srcset in re.findall(r'srcset=["\']([^"\']+)["\']', html, re.I):
        melhor, melhor_peso = None, -1
        for item in srcset.split(","):
            item = item.strip()
            if not item:
                continue
            partes = item.split()
            url = partes[0]
            peso = 0
            if len(partes) > 1:
                desc = partes[-1].lower()
                if desc.endswith("w") and desc[:-1].isdigit():
                    peso = int(desc[:-1])
                elif desc.endswith("x"):
                    try:
                        peso = int(float(desc[:-1]) * 1000)
                    except ValueError:
                        peso = 0
            if peso > melhor_peso:
                melhor_peso, melhor = peso, url
        if melhor:
            cands.append(melhor)

    for attr in ("src", "data-src", "data-lazy-src", "data-original", "data-image", "href"):
        cands.extend(re.findall(
            attr + r'=["\']([^"\']+\.' + _IMG_EXT + r'[^"\']*)["\']', html, re.I
        ))

    cands.extend(re.findall(
        r'url\(["\']?([^)"\']+\.' + _IMG_EXT + r'[^)"\']*)', html, re.I
    ))

    saida, vistos = [], set()
    for u in cands:
        u = (u or "").strip().replace("&amp;", "&")
        if not u:
            continue
        low = u.lower()
        if any(lixo in low for lixo in _IMG_LIXO):
            continue
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = urljoin(base_url, u)
        if not u.startswith("http"):
            continue
        if u in vistos:
            continue
        vistos.add(u)
        saida.append(u)
    return saida


def _imagem_serve(caminho: str, min_w: int = 800, min_h: int = 450) -> bool:
    """Confirma que o arquivo baixado é uma imagem real e grande o bastante."""
    try:
        from PIL import Image
    except Exception:
        # Sem PIL, aceita pelo tamanho em bytes (fallback)
        return os.path.exists(caminho) and os.path.getsize(caminho) >= MIN_IMAGE_SIZE

    try:
        with Image.open(caminho) as im:
            w, h = im.size
            im.verify()
        return w >= min_w and h >= min_h and (w * h) >= (min_w * min_h)
    except Exception:
        return False


def _l2_free_image_source(query: str, dest: str, source_name: str,
                          exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """
    Busca imagem em fonte gratuita via HTML, com validação real do arquivo.

    Só retorna sucesso quando o arquivo baixado é uma imagem válida e grande
    (>= 800x450). Logos, ícones e thumbnails são descartados.
    """
    source = FREE_IMAGE_SOURCES.get(source_name)
    if not source:
        return None
    if source_name not in FREE_IMAGE_SOURCES_APROVADOS:
        # Fonte reprovada no teste real — nunca usar.
        return None

    query_encoded = urllib.parse.quote(query)
    url = source["url"].format(query=query_encoded)
    params = source.get("params", {})
    license_str = source["license"]

    try:
        headers = {"User-Agent": WIKIMEDIA_UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200 or not r.text:
            return None

        candidatos = _extrair_candidatos_imagem(r.text, r.url)
        if not candidatos:
            return None

        import tempfile
        for img_url in candidatos[:15]:
            if exclude_urls and img_url in exclude_urls:
                continue

            fd, tmp = tempfile.mkstemp(suffix=".img", dir=os.path.dirname(os.path.abspath(dest)) or ".")
            os.close(fd)
            try:
                if not _download(img_url, tmp, timeout=20):
                    continue
                if not _imagem_serve(tmp):
                    continue
                # Promove o arquivo válido, normalizando para JPEG
                # (evita WEBP/PNG gravados com extensão .jpg)
                try:
                    from PIL import Image
                    with Image.open(tmp) as im:
                        formato = (im.format or "").upper()
                        if formato in ("JPEG", "JPG"):
                            os.replace(tmp, dest)
                        else:
                            if im.mode in ("RGBA", "LA", "P"):
                                fundo = Image.new("RGB", im.size, (255, 255, 255))
                                conv = im.convert("RGBA")
                                fundo.paste(conv, mask=conv.split()[-1])
                                fundo.save(dest, "JPEG", quality=92)
                            else:
                                im.convert("RGB").save(dest, "JPEG", quality=92)
                except Exception:
                    os.replace(tmp, dest)
                if _imagem_serve(dest):
                    return (img_url, license_str)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
    except Exception as e:
        print(f"    [{source_name} Image] '{query}': {e}")
    return None


def _l2_burst_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Burst by Shopify."""
    return _l2_free_image_source(query, dest, "burst", exclude_urls)


def _l2_pikwizard_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Pikwizard."""
    return _l2_free_image_source(query, dest, "pikwizard", exclude_urls)


def _l2_reshot_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Reshot."""
    return _l2_free_image_source(query, dest, "reshot", exclude_urls)


def _l2_freestocks_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Freestocks.org."""
    return _l2_free_image_source(query, dest, "freestocks", exclude_urls)


def _l2_picography_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Picography."""
    return _l2_free_image_source(query, dest, "picography", exclude_urls)


def _l2_skitterphoto_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Skitterphoto."""
    return _l2_free_image_source(query, dest, "skitterphoto", exclude_urls)


def _l2_littlevisuals_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Little Visuals."""
    return _l2_free_image_source(query, dest, "littlevisuals", exclude_urls)


def _l2_jaymantri_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Jay Mantri."""
    return _l2_free_image_source(query, dest, "jaymantri", exclude_urls)


def _l2_picspree_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Picspree."""
    return _l2_free_image_source(query, dest, "picspree", exclude_urls)


def _l2_libreshot_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no LibreShot."""
    return _l2_free_image_source(query, dest, "libreshot", exclude_urls)


def _l2_startupstockphotos_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Startup Stock Photos."""
    return _l2_free_image_source(query, dest, "startupstockphotos", exclude_urls)


def _l2_rgbstock_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no RGBStock."""
    return _l2_free_image_source(query, dest, "rgbstock", exclude_urls)


def _l2_negativespace_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Negative Space."""
    return _l2_free_image_source(query, dest, "negativespace", exclude_urls)


def _l2_freepik_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Freepik (requer API key)."""
    return _l2_free_image_source(query, dest, "freepik", exclude_urls)


def _l2_picjumbo_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Picjumbo."""
    return _l2_free_image_source(query, dest, "picjumbo", exclude_urls)


def _l2_lifeofpix_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Life of Pix."""
    return _l2_free_image_source(query, dest, "lifeofpix", exclude_urls)


def _l2_depositphotos_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Depositphotos."""
    return _l2_free_image_source(query, dest, "depositphotos", exclude_urls)


def _l2_isorepublic_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no ISO Republic."""
    return _l2_free_image_source(query, dest, "isorepublic", exclude_urls)


def _l2_freeimages_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no FreeImages."""
    return _l2_free_image_source(query, dest, "freeimages", exclude_urls)


def _l2_gratispics_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Gratispics."""
    return _l2_free_image_source(query, dest, "gratispics", exclude_urls)


def _l2_newoldstock_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no New Old Stock."""
    return _l2_free_image_source(query, dest, "newoldstock", exclude_urls)


def _l2_kaboompics_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Kaboompics."""
    return _l2_free_image_source(query, dest, "kaboompics", exclude_urls)


def _l2_freerange_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Freerange Stock."""
    return _l2_free_image_source(query, dest, "freerange", exclude_urls)


def _l2_adobestock_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Adobe Stock."""
    return _l2_free_image_source(query, dest, "adobestock", exclude_urls)


def _l2_stocksnap_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no StockSnap.io."""
    return _l2_free_image_source(query, dest, "stocksnap", exclude_urls)


def _l2_stockvault_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Stockvault."""
    return _l2_free_image_source(query, dest, "stockvault", exclude_urls)


def _l2_foodiesfeed_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Foodiesfeed (especializado em comida)."""
    return _l2_free_image_source(query, dest, "foodiesfeed", exclude_urls)


def _l2_focastock_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no FOCA Stock."""
    return _l2_free_image_source(query, dest, "focastock", exclude_urls)


def _l2_morguefile_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no MorgueFile."""
    return _l2_free_image_source(query, dest, "morguefile", exclude_urls)


def _l2_shutterstock_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Shutterstock."""
    return _l2_free_image_source(query, dest, "shutterstock", exclude_urls)


def _l2_gettyimages_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Getty Images."""
    return _l2_free_image_source(query, dest, "gettyimages", exclude_urls)


def _l2_canva_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no Canva."""
    return _l2_free_image_source(query, dest, "canva", exclude_urls)


def _l2_istock_image(query: str, dest: str, exclude_urls: Optional[set] = None) -> Optional[Tuple[str, str]]:
    """Busca imagem no iStock."""
    return _l2_free_image_source(query, dest, "istock", exclude_urls)



# =============================================================================
# NÍVEL 2 — BANCOS GRATUITOS ADICIONAIS (somente os aprovados em teste real)
# =============================================================================

# Esta lista é preenchida apenas com fontes que comprovadamente baixam uma
# imagem grande e válida (>= 800x450). Veja tools/testar_fontes_midia.py.
# Fontes que não baixam imagem real NÃO entram aqui.
#
# Resultado do teste real em 24/10/2026 (queries "war" e "nature"):
#   4 aprovadas de 35 testadas. As demais são JS-driven, paywall ou só
#   entregam logo/thumbnail — e ficam bloqueadas por FREE_IMAGE_SOURCES_APROVADOS.
FREE_IMAGE_SOURCE_ORDER: List[str] = [
    "reshot",          # 2560x1440 WEBP (convertido para JPEG)
    "negativespace",   # 2048x1367 JPEG
    "freestocks",      # 1024x683 JPEG
    "newoldstock",     # 820x1200 JPEG (vintage P&B)
]

# Quantas fontes extras tentar por cena (limita o tempo de busca).
MAX_FREE_IMAGE_TENTATIVAS_POR_CENA = 4

# Fontes aprovadas no teste real. Qualquer outra é recusada em runtime,
# mesmo que esteja cadastrada em FREE_IMAGE_SOURCES.
FREE_IMAGE_SOURCES_APROVADOS = set(FREE_IMAGE_SOURCE_ORDER)


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
# NÍVEL 4 — GERAÇÃO PRÓPRIA POR IA (Global & Diversa)
# =============================================================================

# Estilos visuais globais para diversidade geográfica
GLOBAL_VISUAL_STYLES = [
    # Ásia
    "cinematic shot in rural China, misty mountains, traditional architecture, golden hour",
    "Japanese countryside, cherry blossoms, ancient temple, soft morning light, 8k",
    "Korean hanok village, snow-covered roofs, winter atmosphere, photorealistic",
    "Indian rural landscape, golden fields, traditional farming, vibrant colors",
    "Southeast Asian rice terraces, Bali Indonesia, dramatic clouds, cinematic",
    "Mongolian steppe, endless grassland, yurt, dramatic sky, wide angle",
    # Europa
    "Medieval European village, cobblestone streets, timber-framed houses, misty dawn",
    "Scottish highlands, loch, castle ruins, dramatic lighting, atmospheric",
    "Mediterranean olive groves, cypress trees, golden sunset, Italy Greece",
    "Eastern European forest, birch trees, morning fog, Slavic atmosphere",
    # Américas
    "Andean mountains Peru, terraced farming, llamas, dramatic clouds, high altitude",
    "Amazon rainforest canopy, biodiversity, shafts of light, Brazil Colombia",
    "North American prairie, vast grassland, bison, storm sky, cinematic",
    "Mexican colonial town, colorful buildings, plaza, golden hour",
    # África
    "East African savanna, acacia trees, wildlife silhouette, sunset, Kenya Tanzania",
    "Moroccan desert, sand dunes, kasbah, starry night, cinematic",
    "Ethiopian highlands, rock-hewn churches, dramatic landscape",
    # Oriente Médio
    "Ancient Persian architecture, intricate tilework, golden light, Iran",
    "Jordanian desert, Petra-like ruins, rose red rock, dramatic shadows",
    # Estilos artísticos/documentais
    "Vintage documentary photography 1950s, black and white, grain, authentic",
    "National Geographic style, vivid colors, perfect composition, storytelling",
    "Cinematic drone aerial, top-down, geometric patterns, abstract beauty",
    "Macro photography, extreme detail, textures, nature close-up",
    "Long exposure, light trails, motion blur, artistic interpretation",
]

def _enhance_prompt_for_global_diversity(base_prompt: str, scene_id: int, topic: str) -> str:
    """
    Enriquece o prompt base com estilo visual global diversificado.
    Rotaciona entre estilos para garantir variedade geográfica e estética.
    """
    import hashlib
    # Seleciona estilo baseado em hash do tópico + scene_id para consistência
    style_idx = int(hashlib.md5(f"{topic}_{scene_id}".encode()).hexdigest()[:8], 16) % len(GLOBAL_VISUAL_STYLES)
    global_style = GLOBAL_VISUAL_STYLES[style_idx]
    
    # Combina: assunto principal + estilo global + qualidades técnicas
    enhanced = f"{base_prompt}, {global_style}, professional documentary cinematography, 8k resolution, highly detailed, masterpiece, shot on ARRI Alexa, anamorphic lens"
    return enhanced


def _l4_pollinations_image(prompt: str, dest: str, seed: Optional[int] = None, scene_id: int = 1, topic: str = "") -> Optional[Tuple[str, str]]:
    """Gera imagem via Pollinations.ai com prompt enriquecido para diversidade global."""
    # Enriquece o prompt com diversidade geográfica/estilística
    enhanced_prompt = _enhance_prompt_for_global_diversity(prompt, scene_id, topic)
    
    enc = urllib.parse.quote(enhanced_prompt)
    seed_param = f"&seed={seed}" if seed is not None else ""
    url = f"https://image.pollinations.ai/prompt/{enc}?width=1920&height=1080&nologo=true{seed_param}"
    try:
        r = requests.get(url, timeout=120)  # Aumentado para 120s
        if r.status_code == 200 and len(r.content) > MIN_IMAGE_SIZE:
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(r.content)
            return (url, "ai_generated_pollinations")
    except Exception as e:
        print(f"    [Pollinations] '{enhanced_prompt[:60]}': {e}")
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

        # Respeita os caminhos absolutos definidos pelo pipeline (agent.py).
        # O workspace de cada produção fica em projetos/<slug>, portanto não
        # se deve procurar ffmpeg/ dentro desse workspace por padrão.
        ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        configured_ffmpeg = str(cfg.get("ffmpeg_path") or "").strip()
        configured_ffprobe = str(cfg.get("ffprobe_path") or "").strip()
        self.ffmpeg_path = configured_ffmpeg if configured_ffmpeg and Path(configured_ffmpeg).is_file() else ""
        self.ffprobe_path = configured_ffprobe if configured_ffprobe and Path(configured_ffprobe).is_file() else ""
        if not self.ffmpeg_path:
            candidates = [self.root / "ffmpeg" / "bin" / ffmpeg_name,
                          Path(__file__).resolve().parent / "ffmpeg" / "bin" / ffmpeg_name,
                          Path(__file__).resolve().parent.parent / "ffmpeg" / "bin" / ffmpeg_name]
            self.ffmpeg_path = next((str(p) for p in candidates if p.is_file()), "") or __import__("shutil").which("ffmpeg") or "ffmpeg"
        if not self.ffprobe_path:
            sibling_probe = Path(self.ffmpeg_path).with_name(ffprobe_name)
            candidates = [sibling_probe,
                          self.root / "ffmpeg" / "bin" / ffprobe_name,
                          Path(__file__).resolve().parent / "ffmpeg" / "bin" / ffprobe_name,
                          Path(__file__).resolve().parent.parent / "ffmpeg" / "bin" / ffprobe_name]
            self.ffprobe_path = next((str(p) for p in candidates if p.is_file()), "") or __import__("shutil").which("ffprobe") or "ffprobe"

        self.videos_dir  = str(self.root / "videos")
        self.imagens_dir = str(self.root / "imagens")
        os.makedirs(self.videos_dir, exist_ok=True)
        os.makedirs(self.imagens_dir, exist_ok=True)

        media_cfg = cfg.get("media", {})
        self.pixabay_key  = media_cfg.get("pixabay_api_key", "")
        self.pexels_key   = media_cfg.get("pexels_api_key", "")
        self.unsplash_key = media_cfg.get("unsplash_api_key", "")
        self.youtube_mode = str(media_cfg.get("youtube_mode", "off") or "off").lower()
        self.youtube_authorized_file = str(media_cfg.get("youtube_authorized_file", "") or "")
        self.youtube_source_url = str(media_cfg.get("youtube_source_url", "") or "")
        self.youtube_rights_confirmed = bool(media_cfg.get("youtube_rights_confirmed", False))
        self._youtube_segment_cursor = 0.0
        self._youtube_segment_source_duration = None
        self._youtube_segment_source_checked = False

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

        # Image Evaluator (valida compatibilidade imagem↔roteiro)
        self.image_evaluator = None
        try:
            from image_evaluator_agent import create_evaluator
            # Usa o executável descoberto pelo pipeline; self.root é o workspace
            # da produção e não necessariamente a raiz onde o FFmpeg foi instalado.
            self.image_evaluator = create_evaluator(cfg, self.root, self.ffmpeg_path)
            print(f"  [ImageEvaluator] Ativado (min_score={self.image_evaluator.min_score})")
        except Exception as e:
            print(f"  [ImageEvaluator] Não disponível: {e}")

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

    def _validate_asset(self, scene: dict, media_path: str, source_name: str) -> bool:
        """
        Valida o asset baixado/gerado com o ImageEvaluatorAgent.
        Retorna True se aprovado, False se reprovado (deve tentar próxima fonte).
        """
        scene_text = scene.get("texto", "") or scene.get("descricao", "")
        query_used = scene.get("query", "") or scene.get("wikimedia_q", "") or scene.get("ai_prompt", "")
        topic = getattr(self, "_current_topic", "documentario")

        # Imagens estáticas: usa o Gemini Web por padrão e exige uma avaliação visual real.
        # Defina VF_GEMINI_VISUAL_EVAL=0 para optar explicitamente pelo avaliador legado.
        gemini_visual = os.environ.get("VF_GEMINI_VISUAL_EVAL", "1").strip().lower() not in {"0", "false", "no", "off"}
        is_video = str(scene.get("tipo", "image")).lower().startswith("video") or media_path.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))
        if gemini_visual and not is_video:
            try:
                from gemini_webchat_image import evaluate_image
                visual = evaluate_image(
                    image_path=media_path,
                    scene_text=scene_text,
                    query_used=query_used,
                    scene_id=int(scene["id"]),
                    topic=topic,
                )
                if not isinstance(visual, dict) or not isinstance(visual.get("approved"), bool):
                    print("    [ImageEval/Gemini] Avaliação visual não confirmada; rejeitando por segurança.")
                    return False
                score = max(0, min(100, int(visual.get("score", 0))))
                reason = str(visual.get("reason", "Sem justificativa retornada"))
                threshold = int(os.environ.get("VF_IMAGE_EVAL_MIN_SCORE", "65"))
                approved = visual["approved"] and score >= threshold
                print(f"    [ImageEval/Gemini] {'✓ APROVADO' if approved else '✗ REPROVADO'} (score={score}, mínimo={threshold}): {reason}")
                if not approved:
                    try:
                        Path(media_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                return approved
            except Exception as exc:
                print(f"    [ImageEval/Gemini] Falha: {exc}; rejeitando imagem sem avaliação visual real.")
                try:
                    Path(media_path).unlink(missing_ok=True)
                except Exception:
                    pass
                return False

        # Vídeos ou modo legado explicitamente selecionado.
        if not self.image_evaluator or not self.image_evaluator.enabled:
            print(f"    [ImageEval] Avaliação legada indisponível/desativada para {source_name}; não aprovar automaticamente.")
            return False

        print(f"    [ImageEval] Avaliando {source_name} para cena {scene['id']:02d}...")
        result = self.image_evaluator.evaluate(
            scene_text=scene_text,
            media_path=media_path,
            query_used=query_used,
            scene_id=scene["id"],
            topic=topic
        )
        
        if result.approved:
            print(f"    [ImageEval] ✓ APROVADO (score={result.score}): {result.reason}")
            return True
        else:
            print(f"    [ImageEval] ✗ REPROVADO (score={result.score}): {result.reason}")
            if result.suggestions:
                print(f"    [ImageEval] Sugestões: {', '.join(result.suggestions[:2])}")
            # Remove o arquivo reprovado
            try:
                if os.path.exists(media_path):
                    os.remove(media_path)
            except Exception:
                pass
            return False

    # ── Fonte YouTube: arquivo local declarado pelo usuário ───────────────────

    def _probe_authorized_video_duration(self) -> Optional[float]:
        """Obtém a duração do arquivo local com ffprobe; não acessa a URL de origem."""
        if self._youtube_segment_source_checked:
            return self._youtube_segment_source_duration
        self._youtube_segment_source_checked = True
        path = self.youtube_authorized_file
        if not path or not Path(path).is_file() or not self.youtube_rights_confirmed:
            return None
        ffprobe = self.ffprobe_path
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=15, check=False
            )
            if proc.returncode == 0:
                duration = float(proc.stdout.strip())
                if duration > 0:
                    self._youtube_segment_source_duration = duration
        except Exception as exc:
            print(f"    [YouTube autorizado] Não foi possível ler a duração do arquivo: {exc}")
        return self._youtube_segment_source_duration

    def _extract_authorized_youtube_segment(self, scene: dict, dest_path: str) -> Optional[Tuple[str, str]]:
        """Extrai um trecho único de arquivo local autorizado; nunca baixa por URL.

        A posição avança sequencialmente pelo arquivo para não repetir o mesmo trecho.
        Se o arquivo acabar, retorna None para que as fontes normais sejam tentadas.
        """
        if self.youtube_mode not in ("authorized", "both"):
            return None
        if not self.youtube_authorized_file or not self.youtube_rights_confirmed:
            return None
        duration = self._probe_authorized_video_duration()
        if not duration:
            print("    [YouTube autorizado] Arquivo indisponível ou ffprobe não conseguiu ler a duração.")
            return None
        start = self._youtube_segment_cursor
        requested = float(scene.get("duration") or 12.0)
        requested = max(1.0, min(requested, 60.0))
        if start >= duration or (duration - start) < min(1.0, requested):
            print("    [YouTube autorizado] Não há mais trechos inéditos; tentando outras fontes.")
            return None
        segment_duration = min(requested, duration - start)
        ffmpeg = self.ffmpeg_path
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", self.youtube_authorized_file,
                 "-t", f"{segment_duration:.3f}", "-map", "0:v:0", "-map", "0:a?",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                 "-c:a", "aac", "-movflags", "+faststart", dest_path],
                capture_output=True, text=True, timeout=180, check=False
            )
            if proc.returncode != 0 or not self._asset_valid(dest_path, is_video=True):
                try:
                    if os.path.exists(dest_path): os.remove(dest_path)
                except Exception:
                    pass
                print(f"    [YouTube autorizado] Extração do trecho falhou; tentando outras fontes.")
                return None
            self._youtube_segment_cursor += segment_duration
            source_url = self.youtube_source_url or Path(self.youtube_authorized_file).name
            rights = "user-attested authorization (not independently verified)"
            print(f"    [YouTube autorizado] Trecho local {start:.1f}-{start + segment_duration:.1f}s extraído.")
            return (source_url, rights)
        except Exception as exc:
            print(f"    [YouTube autorizado] Erro ao extrair trecho: {exc}")
            return None

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
            video_sources = [
                (lambda q, d: _l1_pixabay_video(q, d, self.pixabay_key, exclude_urls=self.used_urls),  "pixabay_video"),
                (lambda q, d: _l1_pexels_video(q, d, self.pexels_key, exclude_urls=self.used_urls),    "pexels_video"),
                (lambda q, d: _l1_wikimedia_video(q, d, exclude_urls=self.used_urls),                  "wikimedia_video"),
                (lambda q, d: _l1_internet_archive_video(q, d, exclude_urls=self.used_urls),           "internet_archive"),
            ]
            if self.youtube_mode in ("cc", "both"):
                video_sources.append((lambda q, d: _l1_ytdlp_video(q, d, exclude_urls=self.used_urls) if _YTDLP_AVAILABLE else None, "ytdlp_cc_video"))
            for source_fn, name in video_sources:
                if source_fn is None:
                    continue
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
                    # Validação de compatibilidade imagem↔roteiro
                    if not self._validate_asset(scene, dest_path, name):
                        self.used_urls.add(url)
                        continue
                    print(f"    [L1-Video] {name} OK — licenca: {lic}")
                    self.used_urls.add(url)
                    if v_hash: self.used_hashes[v_hash] = sid
                    self.used_paths[dest_path] = sid
                    self._record_hit(name)
                    self._add_report(sid, 1, name, url, lic, dest_path, "video")
                    return dest_path
                time.sleep(0.2)

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # FONTE OPCIONAL — trecho de arquivo local cuja reutilização foi declarada
            # pelo usuário. Só entra nos modos authorized/both; nunca usa URL para baixar.
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if is_video and self.youtube_mode in ("authorized", "both"):
                manual_result = self._extract_authorized_youtube_segment(scene, dest_path)
                if manual_result:
                    url, rights_basis = manual_result
                    v_hash = _file_hash(dest_path)
                    if v_hash and v_hash in self.used_hashes:
                        print(f"    [Dedup] Trecho autorizado duplicado; tentando outra fonte.")
                        try: os.remove(dest_path)
                        except Exception: pass
                    elif self._validate_asset(scene, dest_path, "youtube_user_authorized_file"):
                        if v_hash: self.used_hashes[v_hash] = sid
                        self.used_paths[dest_path] = sid
                        self._record_hit("youtube_user_authorized_file")
                        self._add_report(sid, 1, "youtube_user_authorized_file", url, rights_basis, dest_path, "video")
                        # Acrescenta explicitamente a base declarada, sem afirmar que foi
                        # verificada independentemente.
                        self.media_report[-1]["rights_basis"] = "user_attestation"
                        self.media_report[-1]["rights_verified_independently"] = False
                        return dest_path
                    else:
                        try:
                            if os.path.exists(dest_path): os.remove(dest_path)
                        except Exception: pass

            # Fallback: converte para imagem se vídeo não encontrado
            print(f"    [L1] Sem video real — escalando para L2 (imagem)...")
            scene["tipo"]    = "image"
            scene["arquivo"] = scene["arquivo"].replace(".mp4", ".jpg")
            dest_path = self._dest_path(scene)  # Recalcula com novo tipo
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
                    # Validação de compatibilidade imagem↔roteiro
                    if not self._validate_asset(scene, dest_path, name):
                        self.used_urls.add(url)
                        continue
                    print(f"    [L2-Image] {name} OK — licenca: {lic}")
                    self.used_urls.add(url)
                    if i_hash: self.used_hashes[i_hash] = sid
                    self.used_paths[dest_path] = sid
                    self._record_hit(name)
                    self._add_report(sid, 2, name, url, lic, dest_path, "image")
                    return dest_path
                time.sleep(0.2)

        # ── L2 estendido: bancos gratuitos adicionais (só os aprovados) ───────
        for nome_extra in FREE_IMAGE_SOURCE_ORDER[:MAX_FREE_IMAGE_TENTATIVAS_POR_CENA]:
            for q in list(dict.fromkeys([img_query, query])):
                if not q:
                    continue
                result = _l2_free_image_source(q, dest_path, nome_extra,
                                               exclude_urls=self.used_urls)
                if not result:
                    continue
                url, lic = result
                e_hash = _file_hash(dest_path)
                if e_hash and e_hash in self.used_hashes:
                    print(f"    [Dedup] {nome_extra}: duplicata da Cena {self.used_hashes[e_hash]:02d}. Rejeitando...")
                    self.used_urls.add(url)
                    try: os.remove(dest_path)
                    except Exception: pass
                    continue
                if not self._validate_asset(scene, dest_path, nome_extra):
                    self.used_urls.add(url)
                    continue
                print(f"    [L2-{nome_extra}] OK — licenca: {lic}")
                self.used_urls.add(url)
                if e_hash: self.used_hashes[e_hash] = sid
                self.used_paths[dest_path] = sid
                self._record_hit(nome_extra)
                self._add_report(sid, 2, nome_extra, url, lic, dest_path, "image")
                return dest_path

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
                # Validação de compatibilidade imagem↔roteiro
                if not self._validate_asset(scene, dest_path, "openverse"):
                    self.used_urls.add(url)
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
        # NÍVEL 4 — Geração real via Gemini Web (sem Pollinations/PIL como fallback)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        prompt = ai_prompt or img_query or scene.get("descricao", f"Cena {sid}")
        print(f"    [L4-Gemini] Solicitando imagem real ao Gemini para cena {sid:02d}...")
        try:
            from gemini_webchat_image import generate_image
            generated = generate_image(
                prompt=prompt,
                dest_path=dest_path,
                scene_id=sid,
                topic=getattr(self, "_current_topic", "documentario"),
            )
        except Exception as exc:
            print(f"    [L4-Gemini] Falha na integração: {exc}")
            generated = None

        if generated and os.path.isfile(dest_path):
            url, lic = generated
            generated_hash = _file_hash(dest_path)
            if generated_hash and generated_hash in self.used_hashes:
                print(f"    [L4-Gemini] Imagem duplicada; rejeitando e deixando a cena pendente.")
                try: os.remove(dest_path)
                except OSError: pass
                return None
            if not self._validate_asset(scene, dest_path, "gemini_webchat"):
                print(f"    [L4-Gemini] Imagem não aprovada visualmente; cena {sid:02d} pendente.")
                try: os.remove(dest_path)
                except OSError: pass
                return None
            if generated_hash:
                self.used_hashes[generated_hash] = sid
            self.used_paths[dest_path] = sid
            self._record_hit("gemini_webchat")
            self._add_report(sid, 4, "gemini_webchat", url, lic, dest_path, "ai_generated")
            return dest_path

        print(f"    [L4-Gemini] Nenhuma imagem real foi recuperada. Cena {sid:02d} pendente; sem imagem falsa.")
        try:
            if os.path.exists(dest_path): os.remove(dest_path)
        except OSError:
            pass
        return None

    # ── Batch com Auditoria Final Anti-Duplicata ─────────────────────────────

    def _enforce_final_uniqueness(self, scenes: List[dict], asset_map: Dict[int, str]) -> int:
        """Remove duplicatas; substitutas só são aceitas se geradas e avaliadas pelo Gemini."""
        seen: Dict[str, int] = {}
        duplicates_fixed = 0
        scene_by_id = {int(s.get("id")): s for s in scenes if s.get("id") is not None}

        for scene in scenes:
            sid = int(scene["id"])
            path = asset_map.get(sid)
            if not path or not os.path.exists(path):
                continue
            f_hash = _file_hash(path)
            if not f_hash:
                continue
            if f_hash not in seen:
                seen[f_hash] = sid
                continue

            first_sid = seen[f_hash]
            print(f"  [Dedup Final] Cena {sid:02d} duplica Cena {first_sid:02d}; tentando substituta Gemini...")
            new_dest = str(Path(self.imagens_dir) / f"cena_{sid:02d}_unique.jpg")
            replacement = None
            prompt = scene.get("ai_prompt") or scene.get("descricao") or scene.get("texto") or f"Cena {sid}"
            try:
                from gemini_webchat_image import generate_image
                replacement = generate_image(prompt=prompt, dest_path=new_dest, scene_id=sid,
                                             topic=getattr(self, "_current_topic", "documentario"))
            except Exception as exc:
                print(f"  [Dedup Final] Gemini falhou para cena {sid:02d}: {exc}")

            if not replacement or not os.path.isfile(new_dest) or not self._validate_asset(scene, new_dest, "gemini_webchat_dedup"):
                try: Path(new_dest).unlink(missing_ok=True)
                except Exception: pass
                asset_map.pop(sid, None)
                scene["arquivo"] = ""
                print(f"  [Dedup Final] Cena {sid:02d} pendente; sem substituta aprovada.")
                continue

            new_hash = _file_hash(new_dest)
            if not new_hash or new_hash in seen:
                try: Path(new_dest).unlink(missing_ok=True)
                except Exception: pass
                asset_map.pop(sid, None)
                scene["arquivo"] = ""
                print(f"  [Dedup Final] Substituta duplicada/inválida; cena {sid:02d} pendente.")
                continue

            asset_map[sid] = new_dest
            scene["tipo"] = "image"
            scene["arquivo"] = Path(new_dest).name
            seen[new_hash] = sid
            self._add_report(sid, 4, "gemini_webchat", replacement[0], replacement[1], new_dest, "ai_generated")
            duplicates_fixed += 1
        return duplicates_fixed

    def source_all(self, scenes: List[dict], topic: str = "") -> Dict[int, str]:
        """
        Adquire mídia para todas as cenas. Retorna asset_map {scene_id: path}.
        Cenas sem asset válido permanecem pendentes.
        Executa auditoria final de exclusividade (Regra de Ouro Anti-Duplicata).
        """
        # Define tópico para o avaliador de imagens
        self._current_topic = topic or "documentario"
        
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
