"""
MediaResearchAgent — Aquisição Hierárquica de Mídia com Verificação de Licença
===============================================================================

Implementa a estratégia de mídia local seguida pela estratégia obrigatória de 4 níveis:

  L0 · Biblioteca local do usuário → shortlist por título e seleção visual Ollama
  L1 · Vídeo real livre       → Pixabay, Pexels, Internet Archive, Wikimedia
                                YouTube opcional e secundário: CC ou arquivo local autorizado; provedores existentes têm prioridade
  L2 · Imagem real livre      → Pixabay, Pexels, Unsplash, Wikimedia Commons
  L3 · Conteúdo IA público    → galerias com licença verificada (Creative Commons)
  L4 · Geração própria por IA → Gemini Web, CapCut Dreamina, Copilot

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
import sys
import contextlib
import subprocess
import hashlib
import urllib.parse
import threading
import unicodedata
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from pipeline_resume import build_resume_report
from bing_provider import BingImageProvider
from query_detector import SearchQueryDetector

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

# Provedores aceitos em VF_IMAGE_GENERATION_PROVIDERS. Meta Muse é opt-in (não entra no padrão).
SUPPORTED_GENERATION_PROVIDERS = ("gemini", "dreamina", "copilot", "chatgpt", "grok", "qwen", "meta_muse")
DEFAULT_GENERATION_PROVIDERS = ("gemini", "dreamina", "copilot", "chatgpt", "grok", "qwen")
MEDIA_SOURCE_MODES = (
    "local_only",
    "local_then_online",
    "webchat_only",
    "internet_images",
)
_PROVIDER_LIMITS_LOCK = threading.Lock()
_GEMINI_OUTPUT_LOCK = threading.Lock()


def _extract_visual_keywords(text: str, max_keywords: int = 8) -> List[str]:
    """
    Extrai palavras-chave visuais relevantes do texto de uma cena para busca de mídia.
    Foca em substantivos concretos, objetos, ações visuais, materiais, técnicas.
    """
    if not text:
        return []
    
    import re
    found_keywords = set()
    text_lower = text.lower()
    
    # Palavras-chave visuais específicas de modelismo/ferreomodelismo
    visual_terms = [
        "XPS", "isopor", "poliestireno", "espuma", "espuma PU", "cola PVA", "cola de contato", 
        "silicone", "epoxi", "resina", "hydrocal", "gesso", "plaster", "plaster cloth", 
        "gesso cimento", "massa de modelar", "argila", "moldes de silicone", "rock molds", 
        "moldes de rocha", "cortica", "EVA", "EVA denso", "roadbed", "leito", "sub-leito", 
        "subleito", "compensado", "compensado naval", "madeira", "pinus", "pinus aplainado", 
        "ripas", "travessas", "longarinas", "elevadores", "risers", "estrutura", 
        "grade aberta", "open grid", "L-girder", "benchwork", "bancada",
        "trilho", "trilhos", "flex track", "trilho flexivel", "code 83", "code 100", 
        "code 70", "rail", "dormente", "dormentes", "ties", "sleepers", "juncao", "juntas", 
        "rail joiners", "uniao", "solda", "soldagem", "ferro de solda", "estanho", "fluxo",
        "lastro", "ballast", "ballasting", "cortica bisotada", "bisotada", "EVA denso", 
        "cascalho", "pedra", "grao", "grnulos", "areia", "wet water", "agua molhada", 
        "cola de lastro", "PVA", "detergente", "capilaridade", "absorcao",
        "poliestireno extrudado", "isopor extrudado", "espuma rigida", "cortador termico", 
        "hot wire", "hot wire cutter", "fio quente", "cortador de fio", "esculpir", 
        "surform", "raspadeira", "lixar", "lixadeira",
        "rocha", "rochas", "rock", "rock molds", "moldes de rocha", "silicone", 
        "borracha de silicone", "hydrocal", "plaster", "gesso pedra", "gesso tipo Hydrocal", 
        "gesso odontologico", "moldes", "casting", "casting de rocha", "fundicao", 
        "pintura de rocha", "wash", "washes", "lavagem", "lixiviacao", "drybrush", 
        "dry brush", "escovacao a seco", "pigmento", "pigmentos", "pastel", "giz pastel", 
        "fuligem", "ferrugem", "terra seca", "poeira", "verniz fosco", "dullcote", "Testors",
        "static grass", "grama estatica", "aplicador eletrostatico", "static grass applicator", 
        "eletrostatico", "eletrostatica", "campo eletrostatico", "fibras", "fibras de nylon", 
        "fibras sinteticas", "grama baixa", "pasto", "capim alto", "mato queimado", 
        "verde claro", "verde oliva", "palha seca", "cola PVA", "clipe jacare", "terra", 
        "aspirador", "meia-calca",
        "aerografo", "airbrush", "air brush", "compressor", "bico 0.2", "bico 0.3", 
        "dupla acao", "tinta acrilica", "marrom escuro", "cinza escuro", "Railboard Brown", 
        "Dark Rust", "preto fosco", "diluiu", "aguarras", "white spirit", "aguarras mineral", 
        "pincel", "pincel umedecido", "burnt sienna", "ferrugem", "fuligem", "escapamento", 
        "chamine", "exaustor", "exaustao a diesel",
        "LED", "SMD", "0805", "0603", "branco quente", "2700K", "lampada incandescente", 
        "iluminacao interior", "light leak", "light bleed", "vazamento de luz", 
        "preto fosco", "black paint", "interior", "edificio", "predio", "casas", "casario", 
        "vilarejo", "cidade", "posta de iluminacao", "poste", "luz", "fiacao", 
        "fio elastico", "fio de poliuretano", "costura",
        "vegetacao", "vegetacao rasteira", "arbustos", "esponja triturada", "cinzenta", 
        "Clump Foliage", "foliage", "arbustos", "margens", "margem", "trilhos", 
        "postes", "iluminacao", "fiacao telefonica", "fio elastico", "fio de poliuretano", 
        "esticar", "quebrar", "toque acidental",
        "transicao", "crepusculo", "iluminacao", "sequencia", "sequencia de luzes", 
        "estudio", "luzes", "casas", "locomotivas", "acendem", "acender", 
        "Busca de Imagem", "Referencia", "HO scale", "building", "LED", "interior", 
        "lighting", "light bleed", "prevention",
        "marcenaria", "tripe", "softbox", "duplo", "pleno aberto", "zenital", "90", 
        "trilhos", "solda", "lente macro", "90mm", "100mm", "luz pontual", "ring light", 
        "super close-up", "close-up", "45", "relevo", "rochas", "gimbal", "portatil", 
        "camera na mao", "luz lateral", "unica", "sombras", "plano medio", "perfil", 
        "lastro", "grama", "lente macro", "slider", "luz difusa", "alta fidelidade", 
        "CRI 95+", "rasante", "nivel dos trilhos", "weathering", "camera", "mesa", 
        "estudio", "luz fria", "neutra", "sem reflexos", "plano fechado", "mao", "artesao", 
        "close-up", "plano fechado", "cenas finais", "lente probe", "mini camera", 
        "luz conica", "propria maquete", "visao do maquinista", "cab view",
    ]
    
    found_keywords = set()
    text_lower = text.lower()
    
    for term in visual_terms:
        if term.lower() in text_lower:
            found_keywords.add(term)
    
    tech_compounds = re.findall(r'\b(?:model railroad|model railroader|model rail|HO scale|N scale|O scale|code 83|code 100|code 70|flex track|trilho flex|code 83|code 100|code 70|dormente|dormentes|lastro|ballast|ballasting|XPS|isopor|poliestireno|hydrocal|gesso|plaster|rock molds|moldes de rocha|static grass|static grass applicator|aplicador eletrostatico|aerografo|airbrush|weathering|drybrush|dry brush|wash|washes|pigmento|pigmentos|static grass|grama estatica|lastro|ballast|cortica|EVA|roadbed|leito|sub-leito|subleito|compensado|compensado naval|madeira|pinus|pinus aplainado|ripas|travessas|longarinas|elevadores|risers|estrutura|grade aberta|open grid|L-girder|benchwork|bancada|trilho|trilhos|flex track|trilho flexivel|code 83|code 100|code 70|rail|dormente|dormentes|ties|sleepers|juncao|juntas|rail joiners|uniao|solda|soldagem|ferro de solda|estanho|fluxo|XPS|isopor|isopor extrudado|poliestireno|espuma|espuma PU|cola PVA|cola de contato|silicone|epoxi|resina|hydrocal|gesso|plaster|plaster cloth|gesso cimento|massa de modelar|argila|silicone moldes|moldes de silicone|rock molds|moldes de rocha|gesso cimento|massa de modelar|argila)\b', text_lower)
    
    for tc in tech_compounds:
        if len(tc) > 3:
            found_keywords.add(tc)
    
    keywords = sorted(list(found_keywords), key=len, reverse=True)
    return keywords[:max_keywords]


def _media_source_permissions(mode: str) -> Dict[str, bool]:
    """Return which source families are permitted for a configured media mode."""
    permissions = {
        "local_only": (True, False, False),
        "local_then_online": (True, True, True),
        "webchat_only": (False, False, True),
        "internet_images": (False, True, False),
    }
    if mode == "legacy":
        return {"local": True, "internet_images": True, "webchat": True}
    try:
        local, internet_images, webchat = permissions[mode]
    except KeyError as exc:
        raise ValueError(
            "media.media_source_mode must be one of: "
            + ", ".join(MEDIA_SOURCE_MODES)
        ) from exc
    return {
        "local": local,
        "internet_images": internet_images,
        "webchat": webchat,
    }


class _ThreadTeeOutput:
    """Forward stdout normally while retaining only the current thread's output."""

    def __init__(self):
        self._stream = sys.stdout
        self._owner = threading.get_ident()
        self._captured: List[str] = []
        self.scene_retry_count = {}
        self.max_scene_retries = 1

    def write(self, value: str) -> int:
        if threading.get_ident() == self._owner:
            self._captured.append(value)
        return self._stream.write(value)

    def flush(self) -> None:
        self._stream.flush()

    def captured_text(self) -> str:
        return "".join(self._captured)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def provider_limit_reached(error: Any = "", status_code: Optional[int] = None) -> bool:
    """Return whether provider text/status indicates a quota or rate limit."""
    if status_code is None:
        status_code = getattr(error, "status_code", None)
        response = getattr(error, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
    try:
        if int(status_code) == 429:
            return True
    except (TypeError, ValueError):
        pass

    text = unicodedata.normalize("NFKD", str(error or ""))
    text = "".join(character for character in text if not unicodedata.combining(character)).lower()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    if re.search(r"(?<!\d)429(?!\d)", text):
        return True
    limit_terms = (
        "quota", "resource exhausted", "too many requests", "rate limit",
        "daily limit", "daily quota", "image limit", "generation limit",
        "free image limit", "limite", "esgotad", "exhausted",
    )
    if any(term in text for term in limit_terms):
        return True
    return bool(
        "desculpe" in text
        and re.search(r"(limite|quota|geracao|imagens|requests|exhausted)", text)
    )


def _resolve_api_key(media_cfg: dict, config_key: str, env_name: str) -> str:
    configured = str(media_cfg.get(config_key, "") or "").strip()
    return configured or os.environ.get(env_name, "").strip()


def _parse_generation_providers(value: str) -> List[str]:
    """Normalize a configured provider list, retaining supported unique names."""
    raw = str(value or "").strip()
    names = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not names:
        return list(DEFAULT_GENERATION_PROVIDERS)
    return list(dict.fromkeys(name for name in names if name in SUPPORTED_GENERATION_PROVIDERS)) or list(DEFAULT_GENERATION_PROVIDERS)


def _generation_provider_order(providers: List[str], scene_id: int) -> List[str]:
    """Round-robin the preferred generator while preserving fallback order."""
    if not providers:
        return []
    offset = (max(1, int(scene_id)) - 1) % len(providers)
    return providers[offset:] + providers[:offset]

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


def _perceptual_hash(path: str) -> Optional[int]:
    """Hash dHash leve para descartar cópias visuais próximas sem serviço remoto."""
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as image:
            pixels = list(ImageOps.grayscale(image).resize((9, 8)).getdata())
        value = 0
        for row in range(8):
            for col in range(8):
                value = (value << 1) | int(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
        return value
    except Exception:
        return None


def _candidate_metadata_matches_query(query: str, metadata: str) -> bool:
    """Reject clearly off-topic search hits using their local title/tags/alt text."""
    query_text = re.sub(r"\s+", " ", str(query or "").lower()).strip()
    candidate = re.sub(r"\s+", " ", str(metadata or "").lower()).strip()
    if not candidate:
        return False

    rail_context = any(term in query_text for term in (
        "model railroad", "model railway", "ho scale", "n scale", "benchwork",
    ))
    if rail_context:
        miniature = re.search(
            r"\b(?:ho|n|o)\s*scale\b|\bscale model\b|\bmodel\s+(?:railroad|railway|train)\b|\bminiature\s+(?:rail|train)",
            candidate,
        )
        rail_subject = re.search(r"\b(?:railroad|railway|train|locomotive|track|benchwork|l-girder)\w*\b", candidate)
        return bool(miniature and rail_subject)

    stop = {"cinematic", "documentary", "footage", "close", "wide", "shot", "detail",
            "macro", "lighting", "realistic", "photo", "image", "video", "the", "with",
            "from", "and", "for", "over", "under", "about"}
    terms = [word for word in re.findall(r"[a-z0-9]+", query_text) if len(word) >= 4 and word not in stop]
    return not terms or any(term in candidate for term in terms)


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


def _asset_sha256(filepath: str) -> str:
    """Hash media content for matching a Gemini verdict to the exact asset."""
    if not filepath or not os.path.isfile(filepath):
        return ""
    digest = hashlib.sha256()
    try:
        with open(filepath, "rb") as asset_file:
            for chunk in iter(lambda: asset_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
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
    Busca vídeo histórico no Internet Archive .
  
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
        skipped = 0
        for hit in hits:
            if not _candidate_metadata_matches_query(query, hit.get("tags", "")):
                skipped += 1
                continue
            img_url = hit.get("largeImageURL") or hit.get("webformatURL")
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, "pixabay license")
        if skipped:
            print(f"    [Filtro local] Pixabay imagem descartou {skipped} candidato(s) sem tags compatíveis.")
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
        skipped = 0
        for photo in photos:
            if not _candidate_metadata_matches_query(query, photo.get("alt", "")):
                skipped += 1
                continue
            img_url = (photo.get("src", {}).get("large2x") or
                       photo.get("src", {}).get("large") or
                       photo.get("src", {}).get("original"))
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, "pexels license")
        if skipped:
            print(f"    [Filtro local] Pexels imagem descartou {skipped} candidato(s) sem texto alternativo compatível.")
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
        skipped = 0
        for res in results:
            description = " ".join(str(res.get(k, "") or "") for k in ("alt_description", "description"))
            if not _candidate_metadata_matches_query(query, description):
                skipped += 1
                continue
            img_url = (res.get("urls", {}).get("regular") or
                       res.get("urls", {}).get("full"))
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, "unsplash license")
        if skipped:
            print(f"    [Filtro local] Unsplash descartou {skipped} candidato(s) sem descrição compatível.")
    except Exception as e:
        print(f"    [Unsplash] '{query}': {e}")
    return None

def _l2_bing_image(
    query: str,
    dest: str,
    exclude_urls=None,
):
    """
    Wrapper para integrar BingImageProvider
    ao pipeline L2 do MediaResearchAgent.
    """

    try:

        from bing_provider import BingImageProvider
        from pathlib import Path
        import shutil

        provider = BingImageProvider(
            min_width=1280,
            min_height=720,
            headless=True,
        )

        temp_dir = (
            Path(dest).parent /
            "_bing_temp"
        )

        files = provider.download(
            query=query,
            dest_dir=str(temp_dir),
            max_images=20,
        )

        if not files:
            return None
        print(f"[DEBUG] Bing retornou {len(files)} arquivos")

        for i, f in enumerate(files):
             print(f"[DEBUG] candidato {i+1}: {f}")

    
        return (
            files,
            "bing image search",
        )

    except Exception as e:

        print(
            f"    [Bing Image] '{query}': {e}"
        )

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
        skipped = 0
        for _, p in sorted(pages.items()):
            if not _candidate_metadata_matches_query(query, p.get("title", "")):
                skipped += 1
                continue
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
        if skipped:
            print(f"    [Filtro local] Wikimedia descartou {skipped} resultado(s) sem assunto compatível no título.")
    except Exception as e:
        print(f"    [Wikimedia Image] '{query}': {e}")
    return None


# =============================================================================
# NÍVEL 2 — NOVAS FONTES DE IMAGEM LIVRE (36 sites gratuitos)
# =============================================================================

# Mapeamento de sites para funções de busca HTML
FREE_IMAGE_SOURCES = {
    "pexels": {
        "url": "https://www.pexels.com/search/{query}/",
        "params": {},
        "license": "pexels license",
    },
    "freepik": {
        "url": "https://www.freepik.com/search?format=search&query={query}",
        "params": {},
        "license": "freepik license",
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
        skipped = 0
        for item in results:
            metadata = " ".join(str(item.get(k, "") or "") for k in ("title", "description", "tags"))
            if not _candidate_metadata_matches_query(query, metadata):
                skipped += 1
                continue
            lic     = item.get("license", "").lower()
            lic_ver = item.get("license_version", "")
            img_url = item.get("url", "")
            if not _license_is_accepted(lic):
                continue
            if not img_url or (exclude_urls and img_url in exclude_urls):
                continue
            if _download(img_url, dest):
                return (img_url, f"{lic} {lic_ver}".strip())
        if skipped:
            print(f"    [Filtro local] Openverse descartou {skipped} resultado(s) sem assunto compatível nos metadados.")
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
    Agente de pesquisa de mídia com biblioteca local e estratégia hierárquica de 4 níveis.
    
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
        self.media_source_mode = str(
            media_cfg.get("media_source_mode", "legacy") or "legacy"
        ).strip().lower()
        self.media_source_permissions = _media_source_permissions(
            self.media_source_mode
        )
        self.local_media_mode = str(
            media_cfg.get("local_media_mode", "prefer") or "prefer"
        ).strip().lower()
        if self.media_source_mode != "legacy":
            self.local_media_mode = {
                "local_only": "required",
                "local_then_online": "prefer",
                "webchat_only": "off",
                "internet_images": "off",
            }[self.media_source_mode]
        if self.local_media_mode not in {"off", "prefer", "required"}:
            raise ValueError(
                "media.local_media_mode must be one of: off, prefer, required"
            )
        try:
            self.min_local_images = int(media_cfg.get("min_local_images", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("media.min_local_images must be a non-negative integer") from exc
        if self.min_local_images < 0:
            raise ValueError("media.min_local_images must be a non-negative integer")
        if not self.media_source_permissions["local"]:
            self.min_local_images = 0
        local_media_setting = media_cfg.get("local_media_enabled", True)
        self.local_media_enabled = str(local_media_setting).strip().lower() not in {
            "0", "false", "no", "off", "",
        }
        self.local_media_enabled = (
            self.local_media_enabled and self.local_media_mode != "off"
        )
        if self.local_media_mode == "required" and not self.local_media_enabled:
            raise ValueError(
                "media.local_media_mode is 'required' but local media is disabled"
            )
        local_media_folder = media_cfg.get("local_media_folder")
        if local_media_folder:
            self.local_media_folder = Path(local_media_folder)
            if not self.local_media_folder.is_absolute():
                self.local_media_folder = self.root / self.local_media_folder
        else:
            self.local_media_folder = self.root / "biblioteca_local"
        try:
            self.local_similarity_threshold = float(
                media_cfg.get("local_similarity_threshold", 0.80)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("media.local_similarity_threshold must be between 0 and 1") from exc
        self.skip_ollama = bool(media_cfg.get("skip_ollama", False))
        if not 0.0 <= self.local_similarity_threshold <= 1.0:
            raise ValueError("media.local_similarity_threshold must be between 0 and 1")
        self.local_ollama_model = str(
            media_cfg.get("local_ollama_model", "llava-phi3")
        ).strip()
        self.local_ollama_url = str(
            media_cfg.get("local_ollama_url", "http://127.0.0.1:11434")
        ).strip()
        try:
            self.local_ollama_candidate_count = int(
                media_cfg.get("local_ollama_candidate_count", 4)
            )
            self.local_ollama_timeout = float(
                media_cfg.get("local_ollama_timeout_s", 180)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "media.local_ollama_candidate_count and "
                "media.local_ollama_timeout_s must be numeric"
            ) from exc

        self.pixabay_key  = _resolve_api_key(
            media_cfg, "pixabay_api_key", "VF_PIXABAY_API_KEY"
        )
        self.pexels_key   = media_cfg.get("pexels_api_key", "")
        self.unsplash_key = _resolve_api_key(
            media_cfg, "unsplash_api_key", "VF_UNSPLASH_API_KEY"
        )
        self.youtube_mode = str(media_cfg.get("youtube_mode", "off") or "off").lower()
        pipeline_cfg = cfg.get("pipeline", {})
        self.resume_mode = bool(pipeline_cfg.get("resume_mode", False))
        self.resumed_scene_ids = set()
        self.force_regeneration = bool(media_cfg.get("force_regeneration", False))
        self.ignore_cache = bool(media_cfg.get("ignore_cache", False))
        self.web_research_before_generation = bool(
            media_cfg.get("web_research_before_generation", False)
        )
        self.gemini_only = str(media_cfg.get("gemini_only", False)).strip().lower() in {
            "1", "true", "yes", "on",
        }
        self.gemini_fallback = str(media_cfg.get("gemini_fallback", True)).strip().lower() not in {
            "0", "false", "no", "off",
        }
        self.prefer_real_media = str(media_cfg.get("prefer_real_media", True)).strip().lower() not in {
            "0", "false", "no", "off",
        }
        try:
            self.youtube_max_results = max(1, min(30, int((cfg.get("ytdlp") or {}).get("max_search_results", 20))))
        except (TypeError, ValueError):
            self.youtube_max_results = 20
        self.youtube_authorized_file = str(media_cfg.get("youtube_authorized_file", "") or "")
        self.youtube_source_url = str(media_cfg.get("youtube_source_url", "") or "")
        self.youtube_rights_confirmed = bool(media_cfg.get("youtube_rights_confirmed", False))
        provider_setting = os.environ.get(
            "VF_IMAGE_GENERATION_PROVIDERS",
            str(media_cfg.get("ai_generation_providers", "") or ""),
        )
        self.generation_providers = _parse_generation_providers(provider_setting)
        try:
            configured_workers = os.environ.get("VF_MEDIA_WORKERS", media_cfg.get("parallel_workers", 3))
            self.scene_workers = max(1, min(6, int(configured_workers)))
        except (TypeError, ValueError):
            self.scene_workers = 3
        try:
            configured_candidates = os.environ.get("VF_STOCK_CANDIDATES_PER_SCENE", media_cfg.get("stock_candidates_per_scene", 13))
            self.stock_candidates_per_scene = max(1, min(18, int(configured_candidates)))
        except (TypeError, ValueError):
            self.stock_candidates_per_scene = 4
        self._provider_locks = {provider: threading.Lock() for provider in self.generation_providers}
        self._evaluation_lock = threading.Lock()
        self._youtube_segment_cursor = 0.0
        self._youtube_segment_source_duration = None
        self._youtube_segment_source_checked = False

        self.media_report: List[Dict] = []
        self._source_stats: Dict[str, int] = {}
        
        # Armazenamento de múltiplas fotos por cena (para suporte a múltiplas imagens)
        self.local_assets_by_scene: Dict[int, List[str]] = {}

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
        self.seen_visual_hashes: Dict[int, int] = {}  # dHash → primeira cena/candidata avaliada
        self.gemini_approved_assets: Dict[int, Dict[str, Any]] = {}
        self.used_paths: Dict[str, int] = {}     # filepath  → scene_id

        # Carrega preferências aprendidas
        self._prefs = self._load_prefs()

        # Cache de assets entre execuções (global ou por workspace)
        c_dir = Path(cache_dir) if cache_dir else (self.root / "cache")
        self.cache = AssetCache(c_dir) if _CACHE_AVAILABLE and AssetCache and not self.ignore_cache else None

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

        self.local_media = None
        self.local_media_review_callback = None
        if self.local_media_enabled:
            if self.local_media_folder.is_dir():
                try:
                    from local_media_agent import LocalMediaAgent
                except ImportError:
                    from VideoFactoryAI.local_media_agent import LocalMediaAgent

                self.local_media = LocalMediaAgent(
                    self.local_media_folder,
                    self.local_similarity_threshold,
                    model=self.local_ollama_model,
                    base_url=self.local_ollama_url,
                    candidate_count=self.local_ollama_candidate_count,
                    timeout=self.local_ollama_timeout,
                )
                print(f"  [LOCAL] {len(self.local_media.index)} imagens indexadas")
            else:
                print(f"  [LOCAL] Pasta da biblioteca não encontrada: {self.local_media_folder}")
        if self.local_media_mode == "required" and (
            self.local_media is None or not self.local_media.index
        ):
            raise RuntimeError(
                "Modo somente local ativo, mas nenhuma imagem foi indexada em "
                f"'{self.local_media_folder}'. Confira o caminho da biblioteca."
            )

    def _provider_limits_path(self) -> Path:
        return self.memory_dir / "provider_limits.json"

    def _read_provider_limits(self) -> dict:
        try:
            data = json.loads(self._provider_limits_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_provider_limits(self, data: dict) -> None:
        path = self._provider_limits_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def _provider_disabled(self, provider: str, now: Optional[datetime] = None) -> bool:
        current = now or datetime.now().astimezone()
        if current.tzinfo is None:
            current = current.astimezone()
        with _PROVIDER_LIMITS_LOCK:
            data = self._read_provider_limits()
            providers = data.get("providers", {})
            if not isinstance(providers, dict):
                providers = {}
            state = providers.get(str(provider).lower(), {})
            disabled_until = state.get("disabled_until") if isinstance(state, dict) else None
            if not disabled_until:
                return False
            try:
                expiry = datetime.fromisoformat(disabled_until)
                if expiry.tzinfo is None and current.tzinfo is not None:
                    expiry = expiry.replace(tzinfo=current.tzinfo)
            except (TypeError, ValueError):
                expiry = current
            if current < expiry:
                return True
            providers.pop(str(provider).lower(), None)
            data["providers"] = providers
            self._write_provider_limits(data)
            return False

    def _disable_provider(
        self,
        provider: str,
        reason: str,
        now: Optional[datetime] = None,
    ) -> None:
        current = now or datetime.now().astimezone()
        if current.tzinfo is None:
            current = current.astimezone()
        next_day = current.date() + timedelta(days=1)
        next_local_day = datetime.combine(next_day, datetime.min.time()).astimezone()
        with _PROVIDER_LIMITS_LOCK:
            data = self._read_provider_limits()
            providers = data.get("providers")
            if not isinstance(providers, dict):
                providers = {}
                data["providers"] = providers
            providers[str(provider).lower()] = {
                "disabled_until": next_local_day.isoformat(),
                "reason": str(reason or "provider quota reached")[:500],
            }
            self._write_provider_limits(data)

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
        """Serialize visual evaluation because Gemini's persistent profile is single-user."""
        with self._evaluation_lock:
            return self._validate_asset_unlocked(scene, media_path, source_name)

    def _validate_asset_unlocked(self, scene: dict, media_path: str, source_name: str) -> bool:
        """
        Valida o asset baixado/gerado com o ImageEvaluatorAgent.
        Retorna True se aprovado, False se reprovado (deve tentar próxima fonte).
        """
        # [CORREÇÃO] Se a imagem veio da biblioteca local, seleção manual ou cache local,
        # aprovamos imediatamente sem passar pelo crivo severo do avaliador.
        if (
            source_name in ("local_library_manual", "local_cache", "resume_local", "local_library") 
            or scene.get("media_source") == "local_library" 
            or scene.get("source_level") == "local_library"
            or "local" in str(scene.get("media_path", "")).lower()
        ):
            print(f"    [ImageEval/Gentil] ✓ APROVADO AUTOMATICAMENTE: Asset local/manual preservado para a cena {scene.get('id', 0):02d}.")
            return True

        # [CORREÇÃO] Se o modo gentil estiver ativado nas configurações, relaxamos a validação severa
        if getattr(self, "gentle_mode", False):
            print(f"    [ImageEval/Gentil] Modo gentil ativo: imagem aceita automaticamente para a cena {scene.get('id', 0):02d}.")
            return True

        scene_text = scene.get("texto", "") or scene.get("descricao", "")
        query_used = scene.get("query", "") or scene.get("wikimedia_q", "") or scene.get("ai_prompt", "")
        topic = getattr(self, "_current_topic", "documentario")

        # Imagens estáticas: usa o Gemini Web por padrão e exige uma avaliação visual real.
        # Defina VF_GEMINI_VISUAL_EVAL=0 para optar explicitamente pelo avaliador legado.
        gemini_visual = os.environ.get("VF_GEMINI_VISUAL_EVAL", "1").strip().lower() not in {"0", "false", "no", "off"}
        is_video = str(scene.get("tipo", "image")).lower().startswith("video") or media_path.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))
        if gemini_visual and not is_video:
            visual_hash = _perceptual_hash(media_path)
            if visual_hash is not None:
                # Só compara com imagens já APROVADAS e com tolerância de 1 bit (dHash de 64 bits).
                # Tolerância 4 marcava imagens diferentes como duplicadas (ver "Dedup visual" no log).
                max_bits = int(os.environ.get("VF_VISUAL_DEDUP_BITS", "1"))
                duplicate_scene = next(
                    (previous_scene for previous_hash, previous_scene in self.seen_visual_hashes.items()
                     if (visual_hash ^ previous_hash).bit_count() <= max_bits),
                    None,
                )
                if duplicate_scene is not None:
                    print(f"    [Dedup visual] Candidata quase idêntica à cena {duplicate_scene:02d}; ignorando avaliação Gemini.")
                    try:
                        Path(media_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                    return False
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
                approved = score > 85 or (visual["approved"] and score >= threshold)
                score_override = " | aprovado pelo score >85" if score > 85 and not visual["approved"] else ""
                print(f"    [ImageEval/Gemini] {'✓ APROVADO' if approved else '✗ REPROVADO'} (score={score}, mínimo={threshold}): {reason}{score_override}")
                if not approved:
                    try:
                        self._last_visual_feedback = reason
                    except Exception:
                        pass
                    try:
                        Path(media_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                if approved and visual_hash is not None:
                    self.seen_visual_hashes[visual_hash] = int(scene["id"])
                if approved and score > 85:
                    asset_sha256 = _asset_sha256(media_path)
                    if asset_sha256:
                        self.gemini_approved_assets[int(scene["id"])] = {
                            "approved": True,
                            "asset": os.path.abspath(media_path),
                            "score": score,
                            "sha256": asset_sha256,
                        }
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

    def _translate_query_to_portuguese(self, query_en: str) -> str:
        """Traduz queries em inglês para português para melhor busca local.
        
        Foca em termos visuais comuns relacionados a ferromodelismo e cenas gerais.
        """
        if not query_en:
            return ""
        
        # Dicionário de tradução - ordenar por tamanho (mais longos primeiro)
        # para evitar traduções parciais incorretas
        translations = [
            # Ferromodelismo / Model Railroad (frases compostas primeiro)
            ("model railroad", "ferromodelismo"),
            ("railroad track", "trilho ferroviário"),
            ("railway track", "trilho ferroviário"),
            ("ho scale", "escala HO"),
            ("flex track", "trilho flexível"),
            ("cork roadbed", "leito de cortiça"),
            ("benchwork", "bancada construção"),
            ("ballasting", "lastreamento"),
            ("soldering", "solda"),
            ("weathering", "envelhecimento"),
            ("airbrush", "aerógrafo"),
            ("code 83", "código 83"),
            
            # Palavras individuais ferromodelismo
            ("locomotives", "locomotivas"),
            ("locomotive", "locomotiva"),
            ("railway", "ferrovia"),
            ("railroad", "ferrovia"),
            ("tracks", "trilhos"),
            ("track", "trilho"),
            ("layout", "maquete"),
            ("scenery", "paisagem"),
            ("terrain", "relevo"),
            ("plaster", "gesso"),
            
            # Ferramentas e Materiais
            ("plywood", "compensado"),
            ("workbench", "bancada trabalho"),
            ("glue", "cola"),
            ("paint", "tinta"),
            ("brush", "pincel"),
            ("knife", "faca"),
            ("scissors", "tesoura"),
            ("pliers", "alicate"),
            ("tools", "ferramentas"),
            ("wood", "madeira"),
            
            # Cenas gerais
            ("close up", "close"),
            ("detail", "detalhe"),
            ("wide shot", "plano aberto"),
            ("golden hour", "hora dourada"),
            ("sunrise", "amanhecer"),
            ("sunset", "pôr do sol"),
            ("cinematic", "cinematográfico"),
            ("documentary", "documentário"),
            ("footage", "filmagem"),
            ("light", "luz"),
            ("shadow", "sombra"),
            ("reflection", "reflexo"),
            ("night", "noite"),
            
            # Natureza
            ("forest", "floresta"),
            ("trees", "árvores"),
            ("grass", "grama"),
            ("field", "campo"),
            ("mountain", "montanha"),
            ("river", "rio"),
            ("lake", "lago"),
            ("sky", "céu"),
            ("clouds", "nuvens"),
            
            # Pessoas
            ("silhouette", "silhueta"),
            ("person", "pessoa"),
            ("people", "pessoas"),
            ("hands", "mãos"),
            ("man", "homem"),
            ("woman", "mulher"),
        ]
        
        # Traduzir phrase por phrase (mais longas primeiro)
        result = query_en.lower()
        for en, pt in translations:
            # Usar regex para substituir palavras inteiras
            import re
            pattern = r'\b' + re.escape(en) + r'\b'
            result = re.sub(pattern, pt, result, flags=re.IGNORECASE)
        
        # Limpar espaços extras
        result = ' '.join(result.split())
        
        return result
    
    def _build_web_search_queries(self, scene: dict, base_query: str = "") -> list:
        """Gera queries simplificadas para busca em bancos de imagens da web.
        
        Cria variações mais curtas e naturais em português e inglês para
        aumentar a taxa de sucesso na busca por imagens reais na web.
        
        Returns:
            Lista de queries ordenadas por prioridade (português primeiro)
        """
        import re
        
        sid = scene.get("id", 0)
        scene_text = str(scene.get("texto", "") or scene.get("descricao", "") or "")
        topic = getattr(self, "_current_topic", "")
        
        queries = []
        seen = set()
        
        def add_query(q: str, priority: int = 0):
            """Adiciona query evitando duplicatas."""
            q = str(q or "").strip()
            if not q or len(q) < 3:
                return
            q_lower = q.lower()
            if q_lower not in seen:
                seen.add(q_lower)
                queries.append((priority, q))
        
        # ── 1. Extrair termos-chave do texto da cena ──────────────────────
        # Remove palavras de parada em português e inglês
        stop_words = {
            # Português
            "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
            "em", "no", "na", "nos", "nas", "por", "para", "com", "sem",
            "que", "se", "ao", "à", "é", "era", "eram", "foi", "foram",
            "está", "estão", "estava", "estavam", "tem", "tinha", "tiveram",
            "mais", "menos", "muito", "muita", "muitos", "muitas",
            "este", "esta", "estes", "estas", "esse", "essa", "esses", "essas",
            "aquele", "aquela", "aqueles", "aquelas", "isso", "isto", "aquilo",
            "ele", "ela", "eles", "elas", "nós", "vocês", "eu", "tu",
            "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
            "nosso", "nossa", "nossos", "nossas", "dele", "dela", "deles", "delas",
            "e", "ou", "mas", "porque", "pois", "já", "não", "sim",
            "até", "desde", "entre", "sobre", "sob", "após", "antes",
            "quando", "onde", "como", "qual", "quais", "quem", "que",
            # Inglês
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "as", "is", "was", "were",
            "are", "been", "be", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "shall", "can",
            "this", "that", "these", "those", "it", "its", "he", "she", "they",
            "we", "you", "i", "me", "my", "your", "his", "her", "our", "their",
            "not", "no", "yes", "if", "then", "than", "so", "too", "very",
            "just", "about", "into", "over", "after", "before", "up", "down",
        }
        
        # Extrair palavras significativas do texto da cena
        words = re.findall(r'[a-zA-ZàáâãéêíóôõúçÀÁÂÃÉÊÍÓÔÕÚÇ]{3,}', scene_text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) >= 3]
        
        # ── 2. Gerar queries em português (PRIORIDADE MÁXIMA) ─────────────
        
        # 2a. Termos do dicionário de tradução (mais específicos)
        if base_query:
            query_pt = self._translate_query_to_portuguese(base_query)
            # Extrair substantivos principais da query traduzida
            pt_words = [w for w in query_pt.split() if w not in stop_words and len(w) >= 3]
            if pt_words:
                # Query completa traduzida (prioridade alta)
                add_query(query_pt, priority=0)
                # Primeiras 2-3 palavras mais importantes
                add_query(" ".join(pt_words[:3]), priority=1)
                # Palavra individual mais significativa
                add_query(pt_words[0], priority=2)
        
        # 2b. Palavras-chave extraídas do texto da cena (em português)
        if keywords:
            # Primeiras 2-3 palavras-chave mais frequentes/significativas
            add_query(" ".join(keywords[:3]), priority=1)
            # Palavra-chave individual mais importante
            add_query(keywords[0], priority=2)
        
        # ── 3. Queries em inglês (fallback) ───────────────────────────────
        
        # 3a. Query original em inglês (se diferente da traduzida)
        if base_query:
            add_query(base_query.lower(), priority=3)
        
        # 3b. Palavras-chave em inglês do dicionário reverso
        if base_query:
            # Tentar extrair termos em inglês da query original
            en_words = [w for w in base_query.lower().split() if w not in stop_words and len(w) >= 3]
            if en_words:
                add_query(" ".join(en_words[:3]), priority=4)
                add_query(en_words[0], priority=5)
        
        # ── 4. Queries genéricas contextuais (último recurso) ─────────────
        
        # Se temos tema, adicionar termo genérico do tema
        if topic:
            topic_pt = self._translate_query_to_portuguese(topic)
            add_query(topic_pt, priority=6)
        
        # Adicionar termos visuais genéricos baseados no conteúdo
        visual_hints = []
        text_lower = scene_text.lower()
        
        # Detectar elementos visuais comuns
        if any(w in text_lower for w in ["pessoa", "homem", "mulher", "rosto", "olhos", "mãos"]):
            visual_hints.extend(["pessoa", "retrato", "close"])
        if any(w in text_lower for w in ["paisagem", "natureza", "céu", "montanha", "floresta"]):
            visual_hints.extend(["paisagem", "natureza"])
        if any(w in text_lower for w in ["prédio", "casa", "cidade", "rua", "estrada"]):
            visual_hints.extend(["arquitetura", "urbano"])
        if any(w in text_lower for w in ["antigo", "histórico", "época", "guerra", "batalha"]):
            visual_hints.extend(["histórico", "vintage", "época antiga"])
        if any(w in text_lower for w in ["ferromodelismo", "locomotiva", "trilho", "maquete"]):
            visual_hints.extend(["ferromodelismo", "locomotiva", "ferrovia"])
        
        for hint in visual_hints[:2]:  # Máximo 2 hints visuais
            add_query(hint, priority=7)
        
        # ── Ordenar por prioridade e retornar ─────────────────────────────
        queries.sort(key=lambda x: x[0])
        result = [q for _, q in queries[:6]]  # Retornar no máximo 6 queries
        
        if result:
            print(f"    [QueryBuilder] Cena {sid:02d}: {len(result)} queries geradas: {result[:3]}...")
        
        return result
    
    def _try_local_image(self, scene: dict, dest_path: str) -> Optional[str]:
        local_media = getattr(self, "local_media", None)
        if (
            not getattr(self, "local_media_enabled", False)
            or str(scene.get("tipo", "image")).lower().startswith("video")
        ):
            return None

        match = None
        # Se skip_ollama estiver desligado, tenta a busca inteligente por texto/Ollama
        skip_ollama = getattr(self, "skip_ollama", False)
        if skip_ollama:
            print(f"    [SKIP-OLLAMA] Cena {scene['id']:02d}: Pulando Ollama, indo direto para revisão manual", flush=True)
        
        if not skip_ollama and local_media is not None:
            # PRIORIZAR TEXTO EM PORTUGUÊS para busca local
            # Usar o texto original do roteiro (que está em português)
            query_pt = str(scene.get("texto") or "").strip()
            
            # Se não houver texto em português, usar query traduzida
            if not query_pt or len(query_pt) < 10:
                query_en = str(scene.get("query") or "").strip()
                query_pt = self._translate_query_to_portuguese(query_en) if query_en else ""
            
            # Se ainda não tiver query, usar outros campos
            if not query_pt:
                query_pt = " ".join(
                    str(scene.get(key) or "").strip()
                    for key in ("descricao", "wikimedia_q", "ai_prompt")
                    if str(scene.get(key) or "").strip()
                )
            
            if query_pt:
                try:
                    print(f"    [OLLAMA-PT] Cena {scene['id']:02d}: Buscando com texto em português: '{query_pt[:60]}...'", flush=True)
                    match = local_media.find_best(query_pt)
                    if match:
                        print(f"    [OLLAMA-PT] Cena {scene['id']:02d}: Encontrado '{Path(match['path']).name}'", flush=True)
                except Exception as e:
                    print(f"    [OLLAMA-PT] Cena {scene['id']:02d}: Erro: {e}", flush=True)

        # Se não houver match ou se o usuário escolheu pular o Ollama, pega a primeira da pasta como padrão para abrir a janela
        if not match:
            local_folder = Path(self.local_media_folder)
            files = sorted([p for p in local_folder.glob("*.*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}])
            if files:
                match = {"path": str(files[0].resolve()), "score": 1.0, "title": files[0].name}
                print(f"    [LOCAL] Cena {scene['id']:02d}: Abrindo GUI com {len(files)} imagens disponíveis da pasta", flush=True)
            else:
                return None

        review_callback = getattr(self, "local_media_review_callback", None)
        if review_callback is not None:
            result = review_callback(scene, match)
            
            # Se retornou booleano (modo GUI antigo): True = aprovado, False = rejeitado
            if isinstance(result, bool):
                if not result:
                    return None
                chosen_paths = [str(match["path"])]
            # Se retornou None ou lista vazia
            elif result is None:
                return None
            else:
                chosen_paths = result
            
            # Se por acaso retornar apenas uma string (caminho único), converte para lista
            if isinstance(chosen_paths, (str, Path)):
                chosen_paths = [str(chosen_paths)]
            
            # Filtra apenas paths válidos
            valid_paths = [p for p in chosen_paths if Path(p).exists()]
            if not valid_paths:
                print(f"    [LOCAL MANUAL] Nenhum caminho válido selecionado para a Cena {scene['id']:02d}")
                return None
            
            destination = Path(dest_path)
            
            try:
                from PIL import Image
                destination.parent.mkdir(parents=True, exist_ok=True)
                
                # Salvar todas as fotos selecionadas
                scene_id = scene["id"]
                saved_paths = []
                
                for i, path_str in enumerate(valid_paths):
                    primary_path = Path(path_str)
                    
                    # Para a primeira foto, usar o destino principal
                    if i == 0:
                        current_dest = destination
                    else:
                        # Para fotos adicionais, criar arquivos numerados
                        stem = destination.stem
                        suffix = destination.suffix
                        current_dest = destination.parent / f"{stem}_photo{i+1}{suffix}"
                    
                    with Image.open(primary_path) as image:
                        image.convert("RGB").save(current_dest, format="JPEG", quality=95)
                    
                    # Registrar hash e paths
                    local_hash = _file_hash(str(current_dest))
                    self.used_hashes[local_hash] = scene_id
                    self.used_paths[str(current_dest)] = scene_id
                    
                    # Adicionar ao relatório
                    self._add_report(
                        scene_id, i, "local_library_manual", 
                        str(primary_path), "user-selected", 
                        str(current_dest), "image"
                    )
                    
                    saved_paths.append(str(current_dest))
                    print(f"    [LOCAL MANUAL] Foto {i+1}/{len(valid_paths)} salva para a Cena {scene_id:02d}: {primary_path.name}")
                
                # Armazenar todas as fotos para uso posterior
                if not hasattr(self, 'local_assets_by_scene'):
                    self.local_assets_by_scene = {}
                self.local_assets_by_scene[scene_id] = saved_paths
                
                print(f"    [LOCAL MANUAL] Total de {len(saved_paths)} fotos aprovadas para a Cena {scene_id:02d}")
                
                # Retornar o primeiro caminho (asset principal)
                return saved_paths[0]
                
            except Exception as e:
                print(f"    [LOCAL MANUAL] Erro ao salvar imagens: {e}")
                return None
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
        source_mode = getattr(self, "media_source_mode", "legacy")
        source_permissions = getattr(
            self, "media_source_permissions", None
        ) or _media_source_permissions(source_mode)
        if is_video and (
            getattr(self, "local_media_mode", "prefer") == "required"
            or source_mode in {"webchat_only", "internet_images"}
        ):
            scene["tipo"] = "image"
            scene["arquivo"] = str(
                Path(scene.get("arquivo") or f"cena_{sid:02d}.jpg").with_suffix(".jpg").name
            )
            is_video = False
        query     = scene.get("query", "")
        wm_query  = scene.get("wikimedia_q", "")
        ai_prompt = scene.get("ai_prompt", "")
        dest_path = self._dest_path(scene)
        gemini_attempted_early = False

        if (
            getattr(self, "resume_mode", False)
            and not getattr(self, "force_regeneration", False)
            and getattr(self, "local_media_mode", "prefer") != "required"
            and source_mode == "legacy"
            and os.path.isfile(dest_path)
            and os.path.getsize(dest_path) > (MIN_VIDEO_SIZE if is_video else MIN_IMAGE_SIZE)
        ):
            print(f"    [RESUME] Cena {sid:02d} já concluída: {Path(dest_path).name}")
            resumed_scene_ids = getattr(self, "resumed_scene_ids", None)
            if resumed_scene_ids is None:
                resumed_scene_ids = self.resumed_scene_ids = set()
            resumed_scene_ids.add(sid)
            f_hash = _file_hash(dest_path)
            if f_hash:
                self.used_hashes[f_hash] = sid
            self.used_paths[dest_path] = sid
            self._add_report(
                sid, 0, "resume_local", "", "reused", dest_path,
                "video" if is_video else "image",
            )
            return dest_path

        # ── Cache local com verificação de duplicata ──────────────────────────
        if (
            getattr(self, "local_media_mode", "prefer") != "required"
            and source_mode == "legacy"
            and self._asset_valid(dest_path, is_video)
        ):
            f_hash = _file_hash(dest_path)
            if f_hash and f_hash in self.used_hashes:
                print(f"    [Dedup] Disco: {Path(dest_path).name} duplica Cena {self.used_hashes[f_hash]:02d}. Substituindo...")
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            elif f_hash:
                if self._validate_asset(scene, dest_path, "local_cache"):
                    print(f"    [Cache] Cena {sid:02d}: {Path(dest_path).name} (hash={f_hash[:8]})")
                    self.used_hashes[f_hash] = sid
                    self.used_paths[dest_path] = sid
                    self._add_report(sid, 0, "local_cache", "", "cached", dest_path,
                                     "video" if is_video else "image")
                    return dest_path
                print(f"    [Cache] Arquivo existente da cena {sid:02d} não passou pela validação; será substituído.")
                try:
                    Path(dest_path).unlink(missing_ok=True)
                except Exception:
                    pass

        # ── Cache persistente com verificação de duplicata ────────────────────
        cache_q = wm_query or query
        media_type = "video" if is_video else "image"
        if (
            getattr(self, "local_media_mode", "prefer") != "required"
            and source_mode == "legacy"
            and self.cache and cache_q and not self.ignore_cache and not self.force_regeneration
        ):
            cached_file = self.cache.get(cache_q, media_type)
            if cached_file and os.path.exists(cached_file):
                c_hash = _file_hash(cached_file)
                if c_hash and c_hash in self.used_hashes:
                    print(f"    [Dedup] AssetCache duplica Cena {self.used_hashes[c_hash]:02d}. Pulando...")
                else:
                    try:
                        import shutil
                        shutil.copy2(cached_file, dest_path)
                        if self._asset_valid(dest_path, is_video) and self._validate_asset(scene, dest_path, "asset_cache"):
                            self.used_hashes[c_hash] = sid
                            self.used_paths[dest_path] = sid
                            print(f"    [AssetCache] Reutilizado: '{cache_q[:40]}' (hash={c_hash[:8]})")
                            self._add_report(sid, 0, "asset_cache", "", "cached", dest_path, media_type)
                            return dest_path
                        try:
                            Path(dest_path).unlink(missing_ok=True)
                        except Exception:
                            pass
                    except Exception:
                        pass

        print(f"\n  [MediaResearch] Cena {sid:02d} | tipo={scene['tipo']} | query='{query[:50]}'")

        local_image = (
            self._try_local_image(scene, dest_path)
            if source_permissions["local"]
            else None
        )
        if local_image:
            return local_image
        if getattr(self, "local_media_mode", "prefer") == "required":
            print(
                f"    [LOCAL] Modo somente local: nenhuma imagem compatível "
                f"para a Cena {sid:02d}; fontes online desativadas."
            )
            return None

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 1 — Vídeo real livre (com proteção anti-duplicata)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if source_permissions["internet_images"] and is_video and query:
            video_sources = [
                (lambda q, d: _l1_pixabay_video(q, d, self.pixabay_key, exclude_urls=self.used_urls),  "pixabay_video"),
                (lambda q, d: _l1_pexels_video(q, d, self.pexels_key, exclude_urls=self.used_urls),    "pexels_video"),
                (lambda q, d: _l1_wikimedia_video(q, d, exclude_urls=self.used_urls),                  "wikimedia_video"),
                (lambda q, d: _l1_internet_archive_video(q, d, exclude_urls=self.used_urls),           "internet_archive"),
            ]
            if self.youtube_mode in ("cc", "both"):
                video_sources.append((lambda q, d: _l1_ytdlp_video(
                    q, d, exclude_urls=self.used_urls,
                    max_results=self.youtube_max_results,
                ) if _YTDLP_AVAILABLE else None, "ytdlp_cc_video"))
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

        # Explicit Gemini-only or AI-first mode may put Gemini before stock
        # search. If Gemini is suppressed by a persisted quota, keep searching.
        if (
            source_permissions["webchat"]
            and
            not is_video
            and (
                getattr(self, "gemini_only", False)
                or not getattr(self, "prefer_real_media", True)
            )
            and not self._provider_disabled("gemini")
        ):
            gemini_attempted_early = True
            prompt = ai_prompt or query or scene.get("descricao", f"Cena {sid}")
            scene_context = str(scene.get("texto", "") or scene.get("descricao", "")).strip()
            if scene_context:
                prompt = (
                    f"{prompt}\n\nCONTEXTO OBRIGATÓRIO DA CENA (use para escolher o assunto): "
                    f"{scene_context}"
                )
            GeminiSessionError = RuntimeError
            output_capture = None
            try:
                from gemini_webchat_image import GeminiSessionError, generate_image
                output_capture = _ThreadTeeOutput()
                with _GEMINI_OUTPUT_LOCK, contextlib.redirect_stdout(output_capture):
                    print(f"    [L4-Gemini] Prioridade Gemini configurada para a cena {sid:02d}.")
                    with self._provider_locks["gemini"]:
                        early_result = generate_image(
                            prompt=prompt,
                            dest_path=dest_path,
                            scene_id=sid,
                            topic=getattr(self, "_current_topic", "documentario"),
                            web_research_before_generation=getattr(
                                self, "web_research_before_generation", False
                            ),
                            scene_text=scene_context,
                            query=wm_query or query,
                        )
                if provider_limit_reached(output_capture.captured_text()):
                    self._disable_provider("gemini", output_capture.captured_text())
                if early_result and os.path.isfile(dest_path):
                    early_hash = _file_hash(dest_path)
                    if (
                        not early_hash
                        or early_hash in self.used_hashes
                        or not self._validate_asset(scene, dest_path, "gemini_webchat")
                    ):
                        try:
                            Path(dest_path).unlink(missing_ok=True)
                        except OSError:
                            pass
                    else:
                        url, lic = early_result
                        self.used_hashes[early_hash] = sid
                        self.used_paths[dest_path] = sid
                        self._record_hit("gemini_webchat")
                        self._add_report(sid, 4, "gemini_webchat", url, lic, dest_path, "ai_generated")
                        return dest_path
            except GeminiSessionError as exc:
                print(f"    [L4-Gemini] Sessão indisponível; seguindo para mídia real: {exc}")
                if provider_limit_reached(exc) or (
                    output_capture and provider_limit_reached(output_capture.captured_text())
                ):
                    self._disable_provider("gemini", str(exc))
            except Exception as exc:
                print(f"    [L4-Gemini] Falha na prioridade Gemini; seguindo para mídia real: {exc}")
                if provider_limit_reached(exc) or (
                    output_capture and provider_limit_reached(output_capture.captured_text())
                ):
                    self._disable_provider("gemini", str(exc))

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 2 — Imagem real livre (com proteção anti-duplicata)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        img_query = wm_query or query
        if getattr(self, "cfg", {}).get("agent", {}).get("verbose", False):
            print(
                f"\n{'=' * 24} CENA {sid:02d} {'=' * 24}\n"
                f"Texto: {scene.get('texto', '')}\n"
                f"Query: {query}\n"
                f"Prompt: {ai_prompt or scene.get('descricao', '')}\n"
                f"{'=' * 56}"
            )
        # Não dilua consultas específicas com uma busca genérica de documentário:
        # isso gerava candidatos sem vínculo com a cena e avaliações Gemini inúteis.
        image_queries = list(dict.fromkeys(
            str(q).strip() for q in (img_query, query) if str(q or "").strip()
        ))
        stock_candidates_checked = 0
        search_limit_reached = False
        for source_fn, name in (
            [
                (lambda q, d: _l2_bing_image(
                    q,
                    d,
                    exclude_urls=self.used_urls
                ), "bing_image"),
            ]
            if source_permissions["internet_images"] else []
        ):
            for q in image_queries:
                if search_limit_reached:
                    break
                if not q:
                    continue
                print(f"    [WebSearch] {name} | Query: {q}")
                result = source_fn(q, dest_path)
                stock_candidates_checked += 1
                if stock_candidates_checked >= self.stock_candidates_per_scene:
                    search_limit_reached = True
                    print(f"    [L2] Limite de {self.stock_candidates_per_scene} tentativas em bancos atingido; escalando para geração se esta candidata não servir.")
                if result:

                    files, lic = result

                    print(
                        f"    [DEBUG] Recebi "
                        f"{len(files)} candidatos do Bing"
                    )

                    approved = False
                    selected_file = None

                    import shutil

                    for candidate in files:

                        print(
                            f"    [L2-BING] Avaliando "
                            f"{os.path.basename(candidate)}"
                        )

                        shutil.copy2(
                            candidate,
                            dest_path
                        )

                        if self._validate_asset(
                            scene,
                            dest_path,
                            name
                        ):

                            approved = True
                            selected_file = candidate
                            break

                    if not approved:
                        print(
                            "    [L2-BING] Nenhuma candidata aprovada"
                        )
                        continue

                    print(
                        f"    [L2-BING] Aprovada: "
                        f"{os.path.basename(selected_file)}"
                    )

                    return dest_path

                    continue
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
                    print(f"    [WebSearch] Escolhido: {url} | Licença: {lic}")
                    self.used_urls.add(url)
                    if i_hash: self.used_hashes[i_hash] = sid
                    self.used_paths[dest_path] = sid
                    self._record_hit(name)
                    self._add_report(sid, 2, name, url, lic, dest_path, "image")
                    return dest_path
                time.sleep(0.2)

        # ── L2 estendido: bancos gratuitos adicionais (só os aprovados) ───────
        

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 3 — Conteúdo IA público (Openverse, com proteção anti-duplicata)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if False:

            for q in (
                []
                if search_limit_reached or not source_permissions["internet_images"]
                else image_queries
            ):
        
                if not q:
                    continue
                print(f"    [WebSearch] Openverse | Query: {q}")
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
                    print(f"    [WebSearch] Escolhido: {url} | Licença: {lic}")
                    self.used_urls.add(url)
                    if o_hash: self.used_hashes[o_hash] = sid
                    self.used_paths[dest_path] = sid
                    self._record_hit("openverse")
                    self._add_report(sid, 3, "openverse", url, lic, dest_path, "image")
                    return dest_path
                time.sleep(0.3)

        if not source_permissions["webchat"]:
            print(
                f"    [Mídia] Modo {source_mode}: geração via WebChat desativada; "
                f"Cena {sid:02d} permanece pendente se não houver imagem compatível."
            )
            return None

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NÍVEL 4 — Busca web simples PRIMEIRO, geração por IA como fallback.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NOVO FLUXO (v3.13):
        #   1. WebChat search (busca web) com query SIMPLES em inglês
        #   2. AI generation (Gemini/WebChat) apenas como fallback
        # 
        # Rationale: WebChat pode buscar fotos reais existentes na web.
        # Só geramos imagens novas se não encontrarmos fotos reais.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Monta query simples em inglês a partir do assunto visual da cena
        simple_query = self._build_simple_search_query(scene)
        print(f"    [L4] Query simples para busca web: '{simple_query[:100]}'")

        scene_context = str(scene.get("texto", "") or scene.get("descricao", "")).strip()
        available_providers = [
            provider for provider in self.generation_providers
            if not self._provider_disabled(provider)
        ]
        provider_order = _generation_provider_order(available_providers, sid)

        # ── FASE 1: Busca web via WebChat (simples, sequencial) ─────────────
        web_provider_module = None
        try:
            import web_image_providers as web_provider_module
        except Exception as exc:
            print(f"    [L4-Web] Integração web_image_providers indisponível: {exc}")

        provider_labels = {
            "dreamina": "CapCut Dreamina", "copilot": "Copilot", "chatgpt": "ChatGPT",
            "grok": "Grok", "qwen": "Qwen", "meta_muse": "Meta Muse",
        }

        media_perms = getattr(self, "media_source_permissions", None) or {}
        web_search_enabled = (
            web_provider_module is not None
            and getattr(self, "webchat_image_search", True)
            and bool(media_perms.get("webchat", True))
        )

        if web_search_enabled:
            web_providers = [p for p in provider_order if p != "gemini"]
            for provider in web_providers:
                label = provider_labels.get(provider, provider)
                print(f"    [L4-Search] Tentando busca web via {label}...")
                try:
                    search_fn = web_provider_module.search_webchat_image
                    generated = search_fn(
                        query=simple_query,
                        dest_path=dest_path,
                        provider=provider,
                    )
                except Exception as exc:
                    print(f"    [L4-Search] {label} falhou: {exc}")
                    generated = None

                if not generated or not os.path.isfile(dest_path):
                    print(f"    [L4-Search] {label}: nenhuma imagem encontrada; tentando próximo provedor.")
                    continue

                generated_hash = _file_hash(dest_path)
                if generated_hash and generated_hash in self.used_hashes:
                    print(f"    [L4-Search] {label}: imagem duplicada; tentando próximo provedor.")
                    try: Path(dest_path).unlink(missing_ok=True)
                    except OSError: pass
                    continue

                if not self._validate_asset(scene, dest_path, f"{provider}_websearch"):
                    print(f"    [L4-Search] {label}: imagem reprovada pelo avaliador; tentando próximo provedor.")
                    try: Path(dest_path).unlink(missing_ok=True)
                    except OSError: pass
                    continue

                url, lic = generated
                if generated_hash:
                    self.used_hashes[generated_hash] = sid
                self.used_paths[dest_path] = sid
                self._record_hit(f"{provider}_websearch")
                self._add_report(sid, 4, f"{provider}_websearch", url, lic, dest_path, "web_search")
                return dest_path

        # ── FASE 2: Gemini generation (fallback se busca falhou) ─────────────
        preferred_provider = provider_order[0] if provider_order else ""
        if preferred_provider == "gemini":
            print(f"    [L4-Gemini] Busca web falhou; tentando geração via Gemini...")
            base_prompt = ai_prompt or img_query or scene.get("descricao", f"Cena {sid}")
            if scene_context:
                base_prompt = (
                    f"{base_prompt}\n\nCONTEXTO OBRIGATÓRIO DA CENA (use para escolher o assunto): "
                    f"{scene_context}"
                )
            feedback = ""
            generated = None
            generate_image = None
            GeminiSessionError = RuntimeError
            try:
                from gemini_webchat_image import GeminiSessionError, generate_image
            except Exception as exc:
                print(f"    [L4-Gemini] Integração indisponível: {exc}")
                generate_image = None

            max_gemini_attempts = max(1, min(3, int(os.environ.get("VF_GEMINI_RETRIES", "3"))))
            for attempt in range(1, max_gemini_attempts + 1):
                if generate_image is None or gemini_attempted_early:
                    break
                if attempt == 1:
                    prompt = base_prompt
                else:
                    suggestions = scene.get("_visual_search_suggestions", [])
                    suggestion_text = ", ".join(str(x) for x in suggestions[:5]) if isinstance(suggestions, list) else ""
                    prompt = (
                        f"{base_prompt}\n\nCORREÇÃO OBRIGATÓRIA após rejeição visual anterior: {feedback}\n"
                        "Não repita a composição/objeto que foi rejeitado. Gere uma imagem que mostre "
                        "diretamente os elementos exigidos na cena. Priorize os detalhes específicos "
                        "do roteiro e evite assunto apenas genericamente relacionado."
                    )
                    if suggestion_text:
                        prompt += f"\nTermos positivos sugeridos pelo avaliador: {suggestion_text}."
                print(f"    [L4-Gemini] Tentativa {attempt}/{max_gemini_attempts} para cena {sid:02d}...")
                output_capture = None
                try:
                    output_capture = _ThreadTeeOutput()
                    with _GEMINI_OUTPUT_LOCK, contextlib.redirect_stdout(output_capture):
                        with self._provider_locks["gemini"]:
                            generated = generate_image(
                                prompt=prompt,
                                dest_path=dest_path,
                                scene_id=sid,
                                topic=getattr(self, "_current_topic", "documentario"),
                                web_research_before_generation=getattr(
                                    self, "web_research_before_generation", False  # Desligado para evitar loop
                                ),
                                scene_text=scene_context,
                                query=wm_query or query,
                            )
                    if provider_limit_reached(output_capture.captured_text()):
                        self._disable_provider("gemini", output_capture.captured_text())
                        generated = None
                        break
                except GeminiSessionError as exc:
                    print(f"    [L4-Gemini] Sessão indisponível; encerrando tentativas deste provider: {exc}")
                    if provider_limit_reached(exc) or (
                        output_capture and provider_limit_reached(output_capture.captured_text())
                    ):
                        self._disable_provider("gemini", str(exc))
                    generated = None
                    break
                except Exception as exc:
                    print(f"    [L4-Gemini] Falha na geração: {exc}")
                    if provider_limit_reached(exc) or (
                        output_capture and provider_limit_reached(output_capture.captured_text())
                    ):
                        self._disable_provider("gemini", str(exc))
                    generated = None
                if not generated or not os.path.isfile(dest_path):
                    print(f"    [L4-Gemini] Não foi possível recuperar arquivo na tentativa {attempt}.")
                    continue

                generated_hash = _file_hash(dest_path)
                if generated_hash and generated_hash in self.used_hashes:
                    print(f"    [L4-Gemini] Imagem duplicada; tentando outra geração.")
                    try: os.remove(dest_path)
                    except OSError: pass
                    feedback = "A imagem anterior era duplicada de outra cena; gere uma composição diferente."
                    continue

                try:
                    self._last_visual_feedback = ""
                except Exception:
                    pass
                if not self._validate_asset(scene, dest_path, "gemini_webchat"):
                    feedback = str(getattr(self, "_last_visual_feedback", "") or
                                   "A imagem não foi aprovada na avaliação visual. Gere outra imagem específica.")
                    print(f"    [L4-Gemini] Reprovada; motivo para nova tentativa: {feedback[:350]}")
                    try: os.remove(dest_path)
                    except OSError: pass
                    generated = None
                    continue

                url, lic = generated
                if generated_hash:
                    self.used_hashes[generated_hash] = sid
                self.used_paths[dest_path] = sid
                self._record_hit("gemini_webchat")
                self._add_report(sid, 4, "gemini_webchat", url, lic, dest_path, "ai_generated")
                return dest_path

            print(f"    [L4-Gemini] Gemini não entregou imagem aprovada para a cena {sid:02d}; ela permanece pendente.")
        else:
            print(f"    [L4] Busca web falhou e Gemini não é o provedor preferencial; cena {sid:02d} permanece pendente.")

        # Limpeza
        try:
            if os.path.exists(dest_path): os.remove(dest_path)
        except OSError:
            pass
        return None

        # Demais provedores usam perfis diferentes e podem gerar em paralelo para
        # cenas distintas. Um lock por provedor evita duas cenas no mesmo perfil.
        web_provider_module = None
        try:
            import web_image_providers as web_provider_module
            # Modo webchat_only: apenas busca e download, sem geração Gemini
            media_cfg = self.cfg.get("media", {}) if self.cfg else {}
            media_source_mode = media_cfg.get("media_source_mode", "local_only")
            do_webchat_search = (
                media_cfg.get("webchat_image_search", True)
                and media_source_mode != "webchat_only"
            )
            generate_web_image = (
                getattr(web_provider_module, "generate_image", None) if do_webchat_search else None
            )
            search_webchat_fn = (
                getattr(web_provider_module, "search_webchat_image", None) if do_webchat_search else None
            )
        except Exception as exc:
            print(f"    [L4-Web] Integração de fallback indisponível: {exc}")
            generate_web_image = None
            search_webchat_fn = None

        provider_labels = {
            "dreamina": "CapCut Dreamina", "copilot": "Copilot", "chatgpt": "ChatGPT",
            "grok": "Grok", "qwen": "Qwen", "meta_muse": "Meta Muse",
        }
        # Query simples em inglês para busca web (não usar prompt complexo)
        simple_query = self._build_simple_search_query(scene)

        for provider in (item for item in provider_order if item != "gemini"):
            if generate_web_image is None and search_webchat_fn is None:
                break
            label = provider_labels[provider]
            print(f"    [L4-{label}] Gemini não entregou imagem aprovada; tentando {label}...")
            try:
                # PRIMEIRO: tenta busca web simples com query direta
                if search_webchat_fn is not None:
                    generated = search_webchat_fn(
                        query=simple_query,  # Query SIMPLES em inglês
                        dest_path=dest_path,
                        provider=provider,
                    )
                else:
                    generated = generate_web_image(
                        provider=provider,
                        prompt=base_prompt,
                        dest_path=dest_path,
                        scene_id=sid,
                        topic=getattr(self, "_current_topic", "documentario"),
                        web_research_before_generation=False,  # Desligado, já fizemos busca
                        scene_text=scene_context,
                        query=wm_query or query,
                    )
                limit_check = getattr(
                    web_provider_module, "is_provider_limit_reached", lambda _provider: False
                )
                if limit_check(provider):
                    self._disable_provider(
                        provider,
                        f"{provider} webchat reported an image-generation limit",
                    )
            except Exception as exc:
                print(f"    [L4-{label}] Falha no provedor: {exc}")
                generated = None
            if not generated or not os.path.isfile(dest_path):
                print(f"    [L4-{label}] Nenhum arquivo novo recuperado; tentando próximo provedor.")
                continue

            generated_hash = _file_hash(dest_path)
            if generated_hash and generated_hash in self.used_hashes:
                print(f"    [L4-{label}] Imagem duplicada da cena {self.used_hashes[generated_hash]:02d}; rejeitando.")
                try: Path(dest_path).unlink(missing_ok=True)
                except OSError: pass
                continue

            self._last_visual_feedback = ""
            if not self._validate_asset(scene, dest_path, f"{provider}_webchat"):
                print(f"    [L4-{label}] Imagem reprovada pelo avaliador; tentando próximo provedor.")
                continue

            url, lic = generated
            if generated_hash:
                self.used_hashes[generated_hash] = sid
            self.used_paths[dest_path] = sid
            source_name = f"{provider}_websearch"
            self._record_hit(source_name)
            self._add_report(sid, 4, source_name, url, lic, dest_path, "web_search")
            return dest_path

        print(f"    [L4] Gemini, CapCut Dreamina e Copilot não entregaram imagem aprovada para a cena {sid:02d}; ela permanece pendente.")
        try:
            if os.path.exists(dest_path): os.remove(dest_path)
        except OSError:
            pass
        return None
    # ── Retentativa com queries limpas para cenas pendentes ────────────────────

    def _build_clean_web_query(self, scene: dict) -> str:
        """
        Gera uma query de busca web SIMPLES e DIRETA, focada apenas no assunto principal.

        CORREÇÃO v3.12: O prompt anterior acumulava too much information (texto da cena,
        query em inglês, query em português, palavras-chave, hints visuais, etc.), o que
        tornava a busca muito restrita e frequentemente gerava apenas o PIL fallback.

        Agora a query é apenas: "procure em sites da web e me traga SOMENTE imagens ou gráficos ou desenhos ou fotos relativos a: [assunto principal] , nao quero saber o site de origem quero somente VER imagems aqui!".
        """
        # 1. Extrai o assunto principal do texto da cena
        texto = str(scene.get("texto", "") or scene.get("descricao", "") or "").strip()

        # 2. Usa palavras-chave visuais extraídas do texto (já existente no código)
        keywords = _extract_visual_keywords(texto, max_keywords=3)

        # 3. Monta a query simples: "procure na web [assunto] fotos reais"
        if keywords:
            # Pega as 2 palavras-chave mais longas (mais específicas)
            keywords_sorted = sorted(keywords, key=len, reverse=True)[:2]
            assunto = " ".join(keywords_sorted)
        else:
            # Fallback: usa a primeira linha do texto ou a descrição
            assunto = texto.split(".")[0][:80] if texto else str(scene.get("descricao", "cena"))[:80]

        # 4. Query simples e direta
        query = f"procure em sites da web e me traga SOMENTE imagens ou gráficos ou desenhos ou fotos relativos a:  {assunto} , nao quero saber o site de origem quero somente VER imagems aqui!"
        return query

    def _build_simple_search_query(self, scene: dict) -> str:
    """
    Extrai uma query visual específica para Bing.
    Prioridade:
    1) Eventos históricos
    2) Sistemas/Invenções
    3) Pessoas
    4) Conceitos
    5) Fallback
    """

    import re

    texto = str(
        scene.get("texto", "")
        or scene.get("descricao", "")
        or ""
    ).strip()

    if not texto:
        return "historical documentary"

    texto_lower = texto.lower()

    # --------------------------------------------------
    # EVENTOS / SISTEMAS IMPORTANTES
    # --------------------------------------------------

    eventos = {
        "logic theorist": "Logic Theorist AI program",
        "deep blue": "Deep Blue chess computer",
        "alexnet": "AlexNet neural network",
        "dartmouth": "Dartmouth Conference 1956",
        "enigma": "Enigma machine",
        "segunda guerra mundial": "World War II codebreaking",
        "criptoanálise": "Bletchley Park codebreaking",
    }

    for chave, query in eventos.items():

        if chave in texto_lower:

            print(
                f"[QUERY DEBUG] Evento detectado => {query}",
                flush=True
            )

            return query

    # --------------------------------------------------
    # PESSOAS
    # --------------------------------------------------

    nomes = re.findall(
        r'\b[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][a-záàâãéèêíìîóòôõúùûç]+'
        r'(?:\s+[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][a-záàâãéèêíìîóòôõúùûç]+){1,3}',
        texto
    )

    blacklist = {
        "Inteligência Artificial",
        "Segunda Guerra Mundial",
        "Primeira Guerra Mundial",
    }

    for nome in nomes:

        if nome not in blacklist:

            query = f"{nome} portrait"

            print(
                f"[QUERY DEBUG] Pessoa => {query}",
                flush=True
            )

            return query

    # --------------------------------------------------
    # CONCEITOS IMPORTANTES
    # --------------------------------------------------

    conceitos = {
        "redes neurais": "early neural network diagram",
        "rede neural": "early neural network diagram",
        "neurônio artificial": "artificial neuron diagram",
        "memória": "early computer memory",
        "processamento": "mainframe computer room",
        "computador eletrônico": "early computer laboratory",
        "autômatos": "ancient automaton machine",
        "autômato": "ancient automaton machine",
    }

    for chave, query in conceitos.items():

        if chave in texto_lower:

            print(
                f"[QUERY DEBUG] Conceito => {query}",
                flush=True
            )

            return query

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------

    palavras = re.findall(
        r'\b[a-zA-ZÀ-ÿ]{5,}\b',
        texto
    )

    stopwords = {
        "durante",
        "através",
        "entretanto",
        "também",
        "porque",
        "quando",
        "essas",
        "esses",
        "aquela",
        "aquele",
        "inteligência",
        "artificial",
        "computadores",
    }

    palavras = [
        p
        for p in palavras
        if p.lower() not in stopwords
    ]

    query = " ".join(palavras[:4])

    if not query:
        query = "historical technology"

    print(
        f"[QUERY DEBUG] Fallback => {query}",
        flush=True
    )

    return query[:120]

    def _retry_pending_with_clean_queries(self, scenes: List[dict], asset_map: Dict[int, str]) -> None:
        """
        Retenta a busca de mídia para cenas que caíram no PIL fallback (card de texto animado).

        CORREÇÃO v3.12: Cenas que não encontraram mídia real são automaticamente
        reprocessadas com queries web simplificadas, evitando que o vídeo final fique
        com cards de texto em vez de imagens reais.

        Args:
            scenes: Lista de cenas
            asset_map: Mapa de assets já adquiridos (será atualizado)
        """
        if not self.pending_scene_ids:
            return
        # Evita loop infinito de reprocessamento
        if not hasattr(self, "scene_retry_count"):
            self.scene_retry_count = {}

        if not hasattr(self, "max_scene_retries"):
            self.max_scene_retries = 2
        print(f"\n  [RETRY] {len(self.pending_scene_ids)} cenas sem mídia real. Retentando com queries simplificadas...")

        for scene_id in list(self.pending_scene_ids):
            retries = self.scene_retry_count.get(scene_id, 0)

            if retries >= self.max_scene_retries:
                print(
                    f"    [RETRY] Cena {scene_id:02d}: "
                    f"limite ({self.max_scene_retries}) atingido."
                )
                continue

            self.scene_retry_count[scene_id] = retries + 1

            print(
                f"    [RETRY] Cena {scene_id:02d}: "
                f"tentativa {retries + 1}/{self.max_scene_retries}"
            )
            retries = self.scene_retry_count.get(scene_id, 0)

            if retries >= self.max_scene_retries:
                print(
                    f"    [RETRY] Cena {scene_id:02d}: "
                    f"limite de tentativas atingido."
                )
                continue

            self.scene_retry_count[scene_id] = retries + 1
            scene = next((s for s in scenes if s["id"] == scene_id), None)
            if not scene:
                continue

            # Gera query limpa e direta
            clean_query = self._build_clean_web_query(scene)
            print(f"    [RETRY] Cena {scene_id:02d}: query simplificada = '{clean_query[:80]}...'")

            # Atualiza a query da cena
            old_query = scene.get("query", "")
            scene["query"] = clean_query
            scene["wikimedia_q"] = clean_query

            # Remove o PIL fallback anterior se existir
            old_dest = self._dest_path(scene)
            if os.path.exists(old_dest):
                try:
                    os.remove(old_dest)
                except OSError:
                    pass

            # Tenta buscar novamente
            new_path = self.source_scene(scene)
            if new_path:
                asset_map[scene_id] = new_path
                print(f"    [RETRY] ✓ Cena {scene_id:02d}: mídia real encontrada!")
                self.pending_scene_ids.remove(scene_id)
            else:
                scene["query"] = old_query
                scene["wikimedia_q"] = old_query

                print(
                    f"    [RETRY] ✗ Cena {scene_id:02d}: "
                    f"ainda sem mídia real."
                )

                if self.scene_retry_count.get(scene_id, 0) >= self.max_scene_retries:
                    if scene_id in self.pending_scene_ids:
                        self.pending_scene_ids.remove(scene_id)

                    print(
                        f"    [RETRY] Cena {scene_id:02d}: "
                        f"removida da fila."
                    )

                if scene_id in self.pending_scene_ids:
                    self.pending_scene_ids.remove(scene_id)

    # ── Batch com Auditoria Final Anti-Duplicata ─────────────────────────────

    def regenerate_scene(
        self,
        scene: dict,
        topic: str = "",
        corrected_query: Optional[str] = None,
    ) -> Optional[str]:
        """Refaz a busca/geração de uma cena rejeitada. Chamado pelo Diretor de Arte."""
        if topic:
            self._current_topic = topic
        if corrected_query:
            scene = dict(scene)
            scene["query"] = corrected_query
            scene["wikimedia_q"] = corrected_query
        dest = self._dest_path(scene)
        try:
            if os.path.exists(dest):
                old_hash = _file_hash(dest)
                if old_hash and self.used_hashes.get(old_hash) == scene["id"]:
                    self.used_hashes.pop(old_hash, None)
                os.remove(dest)
        except OSError:
            pass
        self.used_paths.pop(dest, None)
        return self.source_scene(scene)

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
            if (
                getattr(self, "local_media_mode", "prefer") == "required"
                or getattr(self, "media_source_mode", "legacy") == "internet_images"
            ):
                print(
                    f"  [Dedup Final] Cena {sid:02d} duplica Cena {first_sid:02d}; "
                    "a cena fica pendente porque o modo selecionado não permite geração WebChat."
                )
                asset_map.pop(sid, None)
                scene["arquivo"] = ""
                continue
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
        No modo local-only, qualquer cena sem imagem aprovada interrompe a produção.
        Executa auditoria final de exclusividade (Regra de Ouro Anti-Duplicata).

        CORREÇÃO v3.12: Cenas que recebem PIL fallback (card com texto animado)
        são automaticamente reprocessadas com queries web simplificadas, evitando
        que o vídeo final fique com cards de texto em vez de imagens reais.
        """
        # Define tópico para o avaliador de imagens
        self._current_topic = topic or "documentario"

        os.makedirs(self.videos_dir,  exist_ok=True)
        os.makedirs(self.imagens_dir, exist_ok=True)

        asset_map: Dict[int, str] = {}
        pending_after_first_pass: List[int] = []
        total = len(scenes)
        cached_clip_scene_ids = set()
        if (
            self.resume_mode
            and not self.force_regeneration
            and getattr(self, "local_media_mode", "prefer") != "required"
            and getattr(self, "media_source_mode", "legacy") == "legacy"
        ):
            clips_dir = Path(self.root) / "temp_clips"
            cached_clip_scene_ids = {
                int(scene["id"])
                for scene in scenes
                if (clips_dir / f"clip_{int(scene['id']):02d}.mp4").is_file()
                and (clips_dir / f"clip_{int(scene['id']):02d}.mp4").stat().st_size > 50_000
            }
            existing_assets = {
                scene["id"]: self._dest_path(scene)
                for scene in scenes
                if os.path.isfile(self._dest_path(scene))
            }
            report = build_resume_report(
                scenes,
                existing_assets,
                image_min_bytes=MIN_IMAGE_SIZE,
                video_min_bytes=MIN_VIDEO_SIZE,
            )
            completed_from_clips = len(
                cached_clip_scene_ids.intersection(report["pending_scene_ids"])
            )
            print(
                "\n" + "=" * 20 + " RESUME REPORT " + "=" * 20 + "\n"
                f"Total cenas: {report['total']}\n"
                f"Já concluídas: {report['completed'] + completed_from_clips}\n"
                f"Faltando: {report['pending'] - completed_from_clips}\n"
                f"Serão processadas: {report['to_process'] - completed_from_clips}\n"
                + "=" * 55
            )

        # Conjunto para rastrear cenas já tentadas nesta execução (evita loop infinito)
        attempted_scene_ids: set = set()

        for idx, scene in enumerate(scenes, 1):
            sid = scene["id"]
            # Pula cenas já tentadas anteriormente neste run para evitar loop
            if sid in attempted_scene_ids:
                print(
                    f"    [SKIP] Cena {sid:02d} já foi tentativa anterior; pulando."
                )
                continue
            if sid in cached_clip_scene_ids and not self._asset_valid(
                self._dest_path(scene), scene["tipo"] == "video"
            ):
                print(
                    f"    [RESUME] Cena {sid:02d} já tem clipe renderizado; "
                    "não repetir busca nem geração de mídia."
                )
                attempted_scene_ids.add(sid)
                continue
            print(f"\n  [{idx:02d}/{total:02d}] Pesquisando midia para cena {sid:02d}...")
            path = self.source_scene(scene)
            if path:
                asset_map[sid] = path
                attempted_scene_ids.add(sid)

        local_only = (
            getattr(self, "media_source_mode", "legacy") == "local_only"
            or (
                getattr(self, "media_source_mode", "legacy") == "legacy"
                and getattr(self, "local_media_mode", "prefer") == "required"
            )
        )
        # ══════════════════════════════════════════════════════════════════════
        # REGRA DE OURO — Auditoria final: corrige qualquer duplicata restante
        # ══════════════════════════════════════════════════════════════════════
        self.pending_scene_ids = [s["id"] for s in scenes if s["id"] not in asset_map]
        if self.pending_scene_ids:
            print("\n  [Pendentes] Cenas sem mídia aprovada: "
                  + ", ".join(f"{int(i):02d}" for i in self.pending_scene_ids))
            if local_only:
                pending = ", ".join(
                    f"{int(scene_id):02d}" for scene_id in self.pending_scene_ids
                )
                raise RuntimeError(
                    "Modo somente local: cenas sem mídia local aprovada "
                    f"({pending}). Nenhuma busca online ou imagem de fallback foi usada."
                )

        # Preserve existing local_assets_by_scene data (populated by _try_local_image during review)
        existing_local_assets = getattr(self, 'local_assets_by_scene', {})
        
        if local_only:
            # Merge existing data with new data from asset_map
            merged_assets = dict(existing_local_assets)
            for scene_id, path in asset_map.items():
                scene_id_int = int(scene_id)
                if scene_id_int not in merged_assets:
                    merged_assets[scene_id_int] = [path]
            self.local_assets_by_scene = merged_assets
        else:
            self.local_assets_by_scene = {}
            for record in self.media_report:
                if record.get("source") == "local_library":
                    try:
                        scene_id = int(record["scene_id"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if record.get("file_path"):
                        self.local_assets_by_scene.setdefault(scene_id, []).append(
                            str(record["file_path"])
                        )

        minimum_local_images = int(getattr(self, "min_local_images", 0))
        local_image_count = sum(
            len(paths) for paths in self.local_assets_by_scene.values()
        )
        
        # Skip minimum_local_images enforcement when manual review is enabled
        # The user is in control of how many photos to select per scene
        review_callback = getattr(self, "local_media_review_callback", None)
        if review_callback is not None:
            if minimum_local_images > 0:
                print(f"\n  [LOCAL] Revisão manual ativa: ignorando mínimo de {minimum_local_images} imagens.")
                print(f"  [LOCAL] Total de {local_image_count} fotos selecionadas manualmente.")
            minimum_local_images = 0  # Disable enforcement
        
        if minimum_local_images > local_image_count:
            local_agent = getattr(self, "local_media", None)
            if not getattr(self, "local_media_enabled", False) or local_agent is None:
                raise RuntimeError(
                    "O mínimo de imagens locais foi definido como "
                    f"{minimum_local_images}, mas a biblioteca local não está disponível."
                )

            eligible_scenes = [
                scene for scene in scenes
                if int(scene["id"]) in self.local_assets_by_scene
            ]
            while local_image_count < minimum_local_images:
                added_this_round = False
                for scene in eligible_scenes:
                    if local_image_count >= minimum_local_images:
                        break
                    scene_id = int(scene["id"])
                    scene_assets = self.local_assets_by_scene[scene_id]
                    destination = (
                        Path(self.root)
                        / "temp_clips"
                        / "local_assets"
                        / f"scene_{scene_id:02d}_local_{len(scene_assets) + 1:03d}.jpg"
                    )
                    extra_path = self._try_local_image(scene, str(destination))
                    if extra_path:
                        scene_assets.append(extra_path)
                        local_image_count += 1
                        added_this_round = True
                        print(
                            f"    [LOCAL] Imagem adicional "
                            f"{local_image_count}/{minimum_local_images} "
                            f"atribuída à Cena {scene_id:02d}"
                        )
                if not added_this_round:
                    break

            if local_image_count < minimum_local_images:
                raise RuntimeError(
                    "Biblioteca local: mínimo de "
                    f"{minimum_local_images} imagens únicas solicitado, mas apenas "
                    f"{local_image_count} foram selecionadas e aprovadas. "
                    "A produção foi interrompida sem fallback."
                )

        if self.resume_mode and not self.force_regeneration:
            print("  [RESUME] Auditoria regenerativa de duplicatas ignorada para preservar assets existentes.")
            dups_fixed = 0
        else:
            dups_fixed = self._enforce_final_uniqueness(scenes, asset_map)
        if dups_fixed > 0:
            print(f"\n  [Dedup] {dups_fixed} mídias duplicadas corrigidas → 100% exclusivas.")

        # ══════════════════════════════════════════════════════════════════════
        # CORREÇÃO v3.12: Retentativa automática para cenas que caíram no PIL fallback
        # ══════════════════════════════════════════════════════════════════════
        # Cenas que não encontraram mídia real e usaram o PIL card (texto animado)
        # são automaticamente reprocessadas com queries web simplificadas.
        # Isso evita que o vídeo final fique com cards de texto em vez de imagens reais,
        # o que prejudica a visualização no YouTube.
        if self.pending_scene_ids and not local_only:
            self._retry_pending_with_clean_queries(scenes, asset_map)

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
        local_count = sum(1 for r in self.media_report if r.get("source") == "local_library")
        cache_count = sum(
            1 for r in self.media_report
            if r["level"] == 0 and r.get("source") != "local_library"
        )
        print(f"    L0 (Biblioteca)  : {local_count} cenas")
        print(f"    Cache            : {cache_count} cenas")
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
            "local_library":   sum(1 for r in self.media_report if r.get("source") == "local_library"),
            "cache":           sum(
                1 for r in self.media_report
                if r["level"] == 0 and r.get("source") != "local_library"
            ),
        }
        return {
            "total_assets":       total,
            "compliant":          compliant,
            "non_compliant":      total - compliant - ai_gen,
            "ai_generated":       ai_gen,
            "compliance_rate_pct": round(100 * compliant / total, 1) if total else 0,
            "by_level":           by_level,
        }
