#!/usr/bin/env python
"""
VideoFactoryAI — Agente Autonomo de Producao de Videos
=======================================================
Transforma um roteiro .txt em documentario 1080p completo.

USO:
    python VideoFactoryAI/agent.py roteiro.txt
    python VideoFactoryAI/agent.py roteiro.txt --resume
    python VideoFactoryAI/agent.py roteiro.txt --canal geopolitica
    python VideoFactoryAI/agent.py roteiro.txt --voice pt-BR-FranciscaNeural
    python VideoFactoryAI/agent.py --help

PASSOS AUTOMATICOS:
    1.  Planejamento de cenas (segmentacao semantica do roteiro)
    2.  Geracao de voz (Edge-TTS neural, sem custo)
    3.  Geracao de legendas (OpenAI Whisper, GPU automatico)
    4.  Busca de midia (hierarquia L1 video real -> L4 IA gerada)
    5.  Processamento visual (Ken Burns + normalizacao 1080p)
    6.  Renderizacao final (FFmpeg concat + audio + legendas)
    7.  Thumbnails multiplas versoes + selecao por contraste
    8.  QualityAgent — verificacao pos-renderizacao
    9.  SeoAgent — metadados YouTube automaticos
    10. Analytics — registro historico de execucao

REUTILIZA (sem modificacao):
    modules/srt_parser.py
    modules/media_engine.py
    modules/visual_processor.py
    modules/composer.py
"""

import os
import sys
import json
import time
import shutil
import argparse
import asyncio
import re
import subprocess
import urllib.parse
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional

# MediaResearchAgent — importação lazy para não falhar se Pillow ausente no import time
_MRA_AVAILABLE = False
try:
    from media_research_agent import MediaResearchAgent as _MRA
    _MRA_AVAILABLE = True
except ImportError:
    _MRA = None  # type: ignore

# Novos agentes — importação lazy com fallback seguro
_QUALITY_AVAILABLE = False
try:
    from quality_agent import QualityAgent as _QA
    _QUALITY_AVAILABLE = True
except ImportError:
    _QA = None  # type: ignore

_SEO_AVAILABLE = False
try:
    from seo_agent import SeoAgent as _SEO
    _SEO_AVAILABLE = True
except ImportError:
    _SEO = None  # type: ignore

_THUMB_AGENT_AVAILABLE = False
try:
    from thumbnail_agent import ThumbnailAgent as _THUMBA
    _THUMB_AGENT_AVAILABLE = True
except ImportError:
    _THUMBA = None  # type: ignore

_ANALYTICS_AVAILABLE = False
try:
    from analytics import Analytics as _ANALYTICS
    _ANALYTICS_AVAILABLE = True
except ImportError:
    _ANALYTICS = None  # type: ignore

_VOICE_MEM_AVAILABLE = False
try:
    from voice_memory import VoiceMemory as _VMEM
    _VOICE_MEM_AVAILABLE = True
except ImportError:
    _VMEM = None  # type: ignore

_CACHE_AVAILABLE = False
try:
    from asset_cache import AssetCache as _CACHE
    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE = None  # type: ignore

_WRITER_AVAILABLE = False
try:
    from script_writer_agent import ScriptWriterAgent as _SWA
    _WRITER_AVAILABLE = True
except ImportError:
    _SWA = None  # type: ignore

# ── Localizar raiz do projeto ─────────────────────────────────────────────────
AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR  = AGENT_DIR.parent

# Adiciona raiz ao path para importar modules/
sys.path.insert(0, str(ROOT_DIR))

# ── Importa módulos existentes (SEM modificação) ──────────────────────────────
from modules.media_engine     import ensure_media_for_scenes
from modules.visual_processor import process_all_scenes
from modules.composer         import assemble_master_documentary

# ── Tenta importar yaml; cai para fallback dict se ausente ───────────────────
try:
    import yaml
    def load_config(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
except ImportError:
    def load_config(path: Path) -> dict:  # type: ignore
        return {}          # usa só os defaults embutidos

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

def get_config(config_path: Path, overrides: dict) -> dict:
    """Carrega config.yaml e aplica overrides da linha de comando."""
    cfg = load_config(config_path)

    # Defaults embutidos (usados mesmo sem yaml instalado)
    defaults = {
        "tts":      {"engine": "edge-tts", "voice": "pt-BR-AntonioNeural",
                     "rate": "+0%", "pitch": "+0Hz",
                     "f5_ref_audio": "voice/minhavoz_curta.wav",
                     "f5_ref_text": ""},
        "whisper":  {"model": "base", "language": "pt", "device": "auto"},
        "scenes":   {"target_duration_s": 12.0, "min_duration_s": 5.0, "max_duration_s": 25.0},
        "media":    {"pixabay_api_key": "58184749-b92df4cd039274d2c7a6aac7a",
                     "ai_image_provider": "pollinations"},
        "video":    {"width": 1920, "height": 1080, "fps": 30, "crf": 20,
                     "preset": "fast", "ken_burns_zoom_speed": 0.0008},
        "subtitles":{"font_size": 24, "margin_v": 35},
        "output":   {"video_filename": "documentario_final.mp4",
                     "thumbnail_filename": "thumbnail.jpg",
                     "thumbnail_width": 1280,
                     "thumbnail_height": 720},
        "agent":    {"checkpoint_enabled": True, "verbose": True,
                     "clean_temp_on_success": False},
    }
    # Merge defaults ← yaml ← CLI overrides (deep, one level)
    for section, vals in defaults.items():
        if section not in cfg:
            cfg[section] = {}
        for k, v in vals.items():
            cfg[section].setdefault(k, v)

    # CLI overrides
    if overrides.get("voice"):
        cfg["tts"]["voice"] = overrides["voice"]
    if overrides.get("whisper_model"):
        cfg["whisper"]["model"] = overrides["whisper_model"]
    if overrides.get("tts_engine"):
        cfg["tts"]["engine"] = overrides["tts_engine"]

    return cfg


# =============================================================================
# PASSO 1 — PLANEJAMENTO DE CENAS
# =============================================================================

HISTORICAL_KEYWORDS = [
    "1953","1979","golpe","mossadegh","shah","pahlavi","khomeini",
    "reféns","embaixada","revolução islâmica","guerra fria",
]
# Para cenas históricas: usa Wikimedia + fallback Pixabay com query genérica
WIKIMEDIA_MAP = {
    "mossadegh":         "Court officials in military trial of Mohammad Mosaddegh",
    "shah":              "Mohammad Reza Pahlavi Shah portrait",
    "pahlavi":           "Mohammad Reza Pahlavi Shah portrait",
    "khomeini":          "Portrait of Ruhollah Khomeini By Ali Kaveh",
    "reféns":            "Iran hostage crisis Tehran 1979 US embassy",
    "golpe":             "1953 Iran coup d'etat Mossadegh protest Tehran",
    "guerra fria":       "Cold War 1950s historical archive",
    "revolução islâmica":"Islamic Revolution Iran 1979 Khomeini historical",
    "embaixada":         "Iran hostage crisis Tehran 1979 US embassy siege",
}
# Fallback Pixabay para cenas históricas quando Wikimedia falha
WIKIMEDIA_PIXABAY_FALLBACK = {
    "mossadegh":         "iran history archive vintage",
    "shah":              "iran history archive vintage middle east",
    "pahlavi":           "iran history archive vintage",
    "khomeini":          "iran revolution crowd vintage protest",
    "reféns":            "protest crowd embassy crisis vintage",
    "golpe":             "protest crowd 1950s historical vintage",
    "guerra fria":       "cold war nuclear bomb vintage archive",
    "revolução islâmica":"crowd protest revolution vintage",
    "embaixada":         "protest crowd embassy crisis vintage",
}
SEMANTIC_QUERIES = {
    # Política / geopolítica
    "bandeiras":       "american flag waving",
    "aliados":         "american flag waving politics",
    "aliança":         "handshake diplomacy meeting politicians",
    "aliadas":         "american flag waving politics",
    "sanções":         "economic sanctions protest inflation market",
    "manchetes":       "news broadcast studio television journalism",
    "geopolítica":     "world map rotating globe geopolitics",
    "tabuleiro":       "chess board strategy game global",
    "xadrez":          "chess board strategy game",
    # Energia
    "petróleo":        "oil pump jack desert oilfield",
    "estreito":        "oil tanker cargo ship sea ocean",
    "ormuz":           "oil tanker cargo ship hormuz sea",
    "refinaria":       "oil refinery industrial plant sunset",
    "posto":           "gas station fuel pump car",
    "combustível":     "gas station fuel pump car",
    "energia":         "nuclear power plant cooling towers",
    # Governo / guerra
    "casa branca":     "white house washington dc government",
    "washington":      "white house washington dc politics",
    "militares":       "aircraft carrier ocean military navy",
    "presença militar":"aircraft carrier ocean military",
    "militar":         "soldiers patrol military desert",
    "guerra":          "military smoke explosion war destruction",
    "confronto":       "military smoke explosion war conflict",
    "custo":           "military smoke explosion war destruction",
    # Nuclear
    "nuclear":         "nuclear power plant cooling towers reactor",
    "urânio":          "nuclear power plant cooling towers",
    "tecnologia":      "laboratory scientist microscope research",
    "científico":      "laboratory scientist microscope research",
    "científica":      "laboratory scientist microscope research",
    # Econômico
    "inflação":        "money counting cash inflation economy",
    "econômica":       "economic market stock trading finance",
    "resistência":     "money counting cash inflation economy",
    "sobrevivência":   "money counting cash inflation economy",
    # Conflitos / crises
    "ciberataque":     "binary code matrix digital data hacker",
    "cibernétic":      "binary code matrix digital data hacker",
    "procuração":      "binary code matrix digital data hacker",
    "refugiados":      "refugee camp humanitarian crisis displaced",
    "humanitária":     "refugee camp humanitarian crisis",
    "tensão":          "military tension standoff armed forces",
    # Diplomacia
    "diplomacia":      "diplomats meeting table negotiation treaty",
    "diplomátic":      "diplomats meeting table negotiation",
    "acordo":          "diplomats meeting table negotiation signing",
    "negociação":      "diplomats meeting table negotiation",
    # ONU / Internacional
    "onu":             "united nations flags international assembly",
    "século xxi":      "united nations flags international diplomacy",
    # Oriente Médio / Irã
    "oriente médio":   "soldiers patrol middle east desert",
    "teerã":           "modern tehran iran city skyline aerial",
    "irã":             "modern tehran iran city skyline aerial",
    "soberania":       "modern tehran iran city skyline aerial",
    # Engajamento / YouTube
    "inscreva":        "youtube subscribe bell button notification",
    "inscrição":       "youtube subscribe bell button notification",
    "like":            "youtube subscribe bell button notification",
    "comentário":      "youtube subscribe bell button notification",
    "comentários":     "youtube subscribe bell button notification",
    "gostou":          "youtube subscribe bell button notification",
}

def _classify_scene(text: str) -> tuple:
    """
    Retorna (tipo, query_pixabay, wikimedia_query, ai_prompt, needs_ai).
    
    Para cenas históricas: tenta Wikimedia primeiro, Pixabay como fallback,
    Pollinations AI como último recurso.
    Para cenas modernas: Pixabay direto.
    """
    low = text.lower()

    # 1. Entidades com fotografia histórica verificada no Wikimedia
    for kw, wm_q in WIKIMEDIA_MAP.items():
        if kw in low:
            # query Pixabay de fallback para o media_engine
            px_fallback = WIKIMEDIA_PIXABAY_FALLBACK.get(kw, "vintage historical archive documentary")
            ai_prompt   = f"Cinematic historical documentary photograph, film grain: {text[:100]}"
            return "image", px_fallback, wm_q, ai_prompt, False  # needs_ai=False → tenta Wikimedia 1o

    # 2. Palavras-chave históricas genéricas → imagem com geração IA
    for kw in HISTORICAL_KEYWORDS:
        if kw in low:
            ai_prompt = (
                f"Cinematic historical documentary photograph, realistic 1970s film grain, "
                f"dramatic lighting, subject: {text[:100]}"
            )
            return "image", "vintage historical archive documentary", "", ai_prompt, True

    # 3. Mapa semântico → vídeo Pixabay
    for kw, en_q in SEMANTIC_QUERIES.items():
        if kw in low:
            return "video", en_q, "", "", False

    # 4. Fallback genérico
    return "video", "geopolitics world news documentary footage", "", "", False

def plan_scenes(script_text: str, cfg: dict) -> List[Dict[str, Any]]:
    """
    Divide o roteiro em cenas de ~target_duration_s segundos
    por contagem de palavras (sem SRT ainda — será ressincronizado depois).
    """
    target_dur   = cfg["scenes"]["target_duration_s"]
    min_dur      = cfg["scenes"]["min_duration_s"]
    words_per_s  = 2.3          # PT-BR a ~138 wpm

    sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
    target_words = int(target_dur * words_per_s)

    scenes, group, wcount, scene_id = [], [], 0, 1
    for sent in sentences:
        group.append(sent)
        wcount += len(sent.split())
        if wcount >= target_words:
            combined = " ".join(group)
            tipo, q_en, wm_q, ai_prompt, needs_ai = _classify_scene(combined)
            ext = ".mp4" if tipo == "video" else ".jpg"
            scenes.append({
                "id":           scene_id,
                "tipo":         tipo,
                "arquivo":      f"cena_{scene_id:02d}{ext}",
                "query":        q_en,
                "wikimedia_q":  wm_q,
                "ai_prompt":    ai_prompt,
                "needs_ai":     needs_ai,
                "descricao":    combined[:80],
                "texto":        combined,
                "start":        0.0,     # preenchido após Whisper
                "end":          0.0,
                "duration":     max(round(wcount / words_per_s, 2), min_dur),
            })
            scene_id += 1
            group, wcount = [], 0

    if group:
        combined = " ".join(group)
        tipo, q_en, wm_q, ai_prompt, needs_ai = _classify_scene(combined)
        ext = ".mp4" if tipo == "video" else ".jpg"
        scenes.append({
            "id":           scene_id,
            "tipo":         tipo,
            "arquivo":      f"cena_{scene_id:02d}{ext}",
            "query":        q_en,
            "wikimedia_q":  wm_q,
            "ai_prompt":    ai_prompt,
            "needs_ai":     needs_ai,
            "descricao":    combined[:80],
            "texto":        combined,
            "start":        0.0,
            "end":          0.0,
            "duration":     max(round(wcount / words_per_s, 2), min_dur),
        })

    return scenes


# =============================================================================
# PASSO 2 — GERAÇÃO DE VOZ (TTS)
# =============================================================================

async def _edge_tts_async(text: str, out: str, voice: str, rate: str, pitch: str):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await comm.save(out)

def generate_voice(text: str, out_path: str, cfg: dict) -> str:
    """Gera narracao.mp3. Retorna path do arquivo gerado."""
    engine = cfg["tts"]["engine"]
    voice  = cfg["tts"]["voice"]
    rate   = cfg["tts"]["rate"]
    pitch  = cfg["tts"]["pitch"]

    if os.path.exists(out_path) and os.path.getsize(out_path) > 50_000:
        log("  [TTS] Narração já existe — pulando geração.")
        return out_path

    log(f"  [TTS] Gerando narração via {engine} (voz: {voice})...")

    if engine == "edge-tts":
        asyncio.run(_edge_tts_async(text, out_path, voice, rate, pitch))

    elif engine == "f5-tts":
        try:
            from f5_tts.api import F5TTS
            ref = cfg["tts"]["f5_ref_audio"]
            ref_text = cfg["tts"]["f5_ref_text"]
            F5TTS().infer(ref_file=ref, ref_text=ref_text,
                          gen_text=text, file_wave=out_path)
        except Exception as e:
            log(f"  [TTS] F5-TTS falhou ({e}) — revertendo para edge-tts.", warn=True)
            asyncio.run(_edge_tts_async(text, out_path, voice, rate, pitch))

    elif engine == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=cfg["media"].get("openai_api_key") or os.getenv("OPENAI_API_KEY"))
            resp = client.audio.speech.create(model="tts-1-hd",
                                              voice=cfg["tts"]["openai_voice"],
                                              input=text)
            resp.stream_to_file(out_path)
        except Exception as e:
            log(f"  [TTS] OpenAI TTS falhou ({e}) — revertendo para edge-tts.", warn=True)
            asyncio.run(_edge_tts_async(text, out_path, voice, rate, pitch))

    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        raise RuntimeError(f"TTS falhou — arquivo de saída inválido: {out_path}")

    size_kb = os.path.getsize(out_path) / 1024
    log(f"  [TTS] Narração gerada: {Path(out_path).name} ({size_kb:.0f} KB)")
    return out_path


# =============================================================================
# PASSO 3 — GERAÇÃO DE LEGENDAS (WHISPER)
# =============================================================================

def _format_ts(s: float) -> str:
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    sc, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sc:02d},{ms:03d}"

def generate_subtitles(audio_path: str, srt_out: str, cfg: dict) -> List[Dict]:
    """Transcreve áudio com Whisper, escreve SRT, retorna blocos."""
    if os.path.exists(srt_out) and os.path.getsize(srt_out) > 500:
        log("  [Whisper] SRT existente — fazendo parse sem re-transcrever.")
        return _parse_srt(srt_out)

    import whisper, torch
    model_name = cfg["whisper"]["model"]
    device_cfg = cfg["whisper"]["device"]
    device = ("cuda" if torch.cuda.is_available() else "cpu") \
             if device_cfg == "auto" else device_cfg

    log(f"  [Whisper] Carregando modelo '{model_name}' em '{device}'...")
    model = whisper.load_model(model_name, device=device)

    log(f"  [Whisper] Transcrevendo '{Path(audio_path).name}'...")
    result = model.transcribe(audio_path,
                               language=cfg["whisper"]["language"],
                               verbose=False)
    segments = result.get("segments", [])
    blocks   = []

    os.makedirs(os.path.dirname(os.path.abspath(srt_out)), exist_ok=True)
    with open(srt_out, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            st  = round(float(seg["start"]), 3)
            et  = round(float(seg["end"]),   3)
            txt = seg["text"].strip()
            f.write(f"{i}\n{_format_ts(st)} --> {_format_ts(et)}\n{txt}\n\n")
            blocks.append({"id": i, "start": st, "end": et,
                            "duration": round(et - st, 3), "text": txt})

    log(f"  [Whisper] {len(blocks)} blocos de legenda gerados.")
    return blocks

def _parse_srt(srt_path: str) -> List[Dict]:
    """Parse de SRT existente em blocos estruturados."""
    with open(srt_path, encoding="utf-8-sig") as f:
        content = f.read()
    pattern = re.compile(
        r'(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n([\s\S]*?)(?=\n\s*\d+\s*\n|\Z)'
    )
    def pt(ts):
        h, m, s = ts.replace(",", ".").split(":")
        return int(h)*3600 + int(m)*60 + float(s)
    return [{"id": int(m[0]), "start": round(pt(m[1]), 3), "end": round(pt(m[2]), 3),
             "duration": round(pt(m[2]) - pt(m[1]), 3),
             "text": re.sub(r'\s+', ' ', m[3]).strip()}
            for m in pattern.findall(content)]


# =============================================================================
# PASSO 3b — RESSINCRONIZAÇÃO DOS TIMECODES
# =============================================================================

def resync_scenes(scenes: List[Dict], blocks: List[Dict], total_dur: float) -> List[Dict]:
    """
    Distribui os blocos Whisper pelas cenas proporcionalmente,
    snappando em fins de frase para cortes naturais.
    """
    if not scenes or not blocks:
        return scenes

    bps     = max(1, len(blocks) // len(scenes))
    cursor  = 0
    updated = []

    for i, scene in enumerate(scenes):
        is_last  = i == len(scenes) - 1
        end_idx  = min(cursor + bps, len(blocks) - 1)

        if not is_last:
            for j in range(end_idx, min(end_idx + 4, len(blocks))):
                if re.search(r'[.!?]$', blocks[j]["text"].strip()):
                    end_idx = j; break

        if is_last:
            end_idx = len(blocks) - 1

        st = blocks[cursor]["start"]
        et = (total_dur if is_last else blocks[end_idx]["end"])
        updated.append({**scene,
                        "start":    round(st, 3),
                        "end":      round(et, 3),
                        "duration": round(max(et - st, 1.0), 3)})
        cursor = end_idx + 1
        if cursor >= len(blocks):
            cursor = len(blocks) - 1

    return updated


# =============================================================================
# PASSO 4 — BUSCA DE MÍDIA (reutiliza modules/media_engine.py)
# =============================================================================
# A função ensure_media_for_scenes() está importada no topo.
# Ela já trata Pixabay + Wikimedia + fallback local.
# Para cenas que precisam de IA (needs_ai=True), usamos Pollinations abaixo.

def _pollinations(prompt: str, dest: str) -> bool:
    enc = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{enc}?width=1920&height=1080&nologo=true"
    try:
        r = requests.get(url, timeout=35)
        if r.status_code == 200 and len(r.content) > 15_000:
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        log(f"  [Pollinations] Erro: {e}", warn=True)
    return False

def source_media(scenes: List[Dict], cfg: dict, root: Path) -> Dict[int, str]:
    """
    Orquestra busca de mídia em 3 camadas:
    1. ensure_media_for_scenes() [Pixabay + Wikimedia, módulo existente]
       - Para cenas Wikimedia, substitui temporariamente o campo 'query' pelo
         wikimedia_q antes de chamar o módulo, e restaura depois.
    2. Para cenas needs_ai: Pollinations AI gratuita (1920x1080)
    3. Fallback PIL procedural (nunca deixa cena sem asset)
    """
    videos_dir  = str(root / "videos")
    imagens_dir = str(root / "imagens")
    api_key     = cfg["media"]["pixabay_api_key"]

    # Prepara cópias das cenas com query correta para o módulo existente
    scenes_for_module = []
    for s in scenes:
        s_copy = dict(s)
        # Se tem wikimedia_q, coloca como query principal para o módulo
        # (media_engine.py usa campo 'query' para busca)
        if s.get("wikimedia_q"):
            s_copy["query"] = s["wikimedia_q"]
        elif s.get("needs_ai") and not s.get("query"):
            # Garante query não-vazia para o módulo não quebrar
            s_copy["query"] = "vintage historical archive documentary"
        scenes_for_module.append(s_copy)

    # Chama módulo existente (Pixabay + Wikimedia + fallback local)
    asset_map = ensure_media_for_scenes(scenes_for_module, videos_dir, imagens_dir, api_key)

    # Cenas ainda não resolvidas → tentar Pollinations AI ou PIL
    for scene in scenes:
        sid = scene["id"]
        if sid in asset_map:
            continue

        dest = str(Path(imagens_dir) / scene["arquivo"].replace(".mp4", ".jpg"))
        prompt = scene.get("ai_prompt") or scene.get("descricao") or scene["texto"][:120]

        log(f"  [Passo 4] Cena {sid:02d} — gerando imagem IA via Pollinations...")
        ok = _pollinations(prompt, dest)

        if ok:
            asset_map[sid] = dest
            # Atualiza tipo em scenes para o visual_processor saber que é imagem
            for s in scenes:
                if s["id"] == sid:
                    s["tipo"]    = "image"
                    s["arquivo"] = Path(dest).name
            log(f"  [Pollinations] Cena {sid:02d} OK.")
        else:
            log(f"  [PIL Fallback] Cena {sid:02d} — usando card procedural.", warn=True)
            _pil_fallback(scene.get("descricao", f"Cena {sid}"), dest)
            asset_map[sid] = dest
            for s in scenes:
                if s["id"] == sid:
                    s["tipo"]    = "image"
                    s["arquivo"] = Path(dest).name

    return asset_map

def _pil_fallback(title: str, dest: str):
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (1920, 1080), (15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.text((80, 500), title[:80], fill=(240, 240, 240))
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    img.save(dest, "JPEG", quality=85)


# =============================================================================
# PASSO 7 — THUMBNAIL
# =============================================================================

def generate_thumbnail(first_asset: str, out_path: str, title: str,
                       w: int = 1280, h: int = 720):
    from PIL import Image, ImageDraw
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    try:
        if first_asset.lower().endswith((".jpg", ".jpeg", ".png")):
            img = Image.open(first_asset).convert("RGB").resize((w, h), Image.LANCZOS)
        else:
            img = Image.new("RGB", (w, h), (15, 23, 42))
        draw = ImageDraw.Draw(img)
        # Gradiente escuro no rodapé
        for y in range(h // 2, h):
            alpha = int(180 * (y - h // 2) / (h // 2))
            r, g, b = img.getpixel((w // 2, y))
            draw.line([(0, y), (w, y)],
                      fill=(int(r*(1-alpha/255)), int(g*(1-alpha/255)), int(b*(1-alpha/255))))
        draw.text((30, h - 60), title[:60], fill=(255, 255, 255))
        img.save(out_path, "JPEG", quality=92)
        log(f"  [Thumbnail] {Path(out_path).name} gerada.")
    except Exception as e:
        log(f"  [Thumbnail] Erro: {e}", warn=True)


# =============================================================================
# CHECKPOINT
# =============================================================================

def save_checkpoint(state: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_checkpoint(path: Path) -> dict:
    if path.exists() and path.stat().st_size > 2:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# =============================================================================
# UTILIDADES
# =============================================================================

_VERBOSE = True

def log(msg: str, warn: bool = False):
    if _VERBOSE or warn:
        prefix = "[WARN]" if warn else "[INFO]"
        print(f"{prefix} {msg}")

def get_audio_duration_simple(ffmpeg: str, audio: str) -> float:
    """Extrai duração do áudio via ffmpeg."""
    res = subprocess.run([ffmpeg, "-i", audio],
                         stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res.stderr)
    if m:
        h, mn, s = m.groups()
        return int(h)*3600 + int(mn)*60 + float(s)
    return 0.0


# =============================================================================
# ARGPARSER
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        prog="VideoFactoryAI",
        description="Transforma um roteiro .txt em documentário 1080p."
    )
    p.add_argument("roteiro", nargs="?", default=None,
                   help="Caminho do roteiro .txt (opcional se usar --topic)")
    p.add_argument("--topic",
                   default=None,
                   metavar="TEMA",
                   help="Tema para geracao automatica completa do documentario (dispensa roteiro.txt)")
    p.add_argument("--duration",
                   type=float,
                   default=5.0,
                   metavar="MIN",
                   help="Duracao estimada em minutos para o modo --topic (padrao: 5)")
    p.add_argument("--voice",
                   default=None,
                   help="Voz Edge-TTS (ex: pt-BR-FranciscaNeural)")
    p.add_argument("--tts-engine",
                   choices=["edge-tts", "f5-tts", "openai"],
                   default=None)
    p.add_argument("--whisper-model",
                   choices=["tiny", "base", "small", "medium", "large"],
                   default=None)
    p.add_argument("--resume",
                   action="store_true",
                   help="Retoma do último checkpoint")
    p.add_argument("--no-checkpoint",
                   action="store_true",
                   help="Desabilita salvamento de checkpoint")
    p.add_argument("--canal", "--channel",
                   default=None,
                   dest="canal",
                   metavar="NOME",
                   help="Canal de producao (ex: documentario, geopolitica, historia, tecnologia)")
    p.add_argument("--pexels-key",
                   default=None,
                   dest="pexels_key",
                   help="Chave da API Pexels (L1/L2 media)")
    p.add_argument("--unsplash-key",
                   default=None,
                   dest="unsplash_key",
                   help="Chave da API Unsplash (L2 imagens)")
    return p.parse_args()


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def main():
    global _VERBOSE
    args = parse_args()

    # ── Localiza, lê ou GERA o roteiro (--topic) ─────────────────────────────
    if getattr(args, "topic", None):
        if not _WRITER_AVAILABLE:
            print("Erro: ScriptWriterAgent nao disponivel.", file=sys.stderr)
            sys.exit(1)
        writer = _SWA(ROOT_DIR)
        canal_chosen = getattr(args, "canal", None)
        script_text, roteiro_path = writer.generate(
            topic=args.topic,
            duration_min=args.duration,
            canal=canal_chosen
        )
    elif args.roteiro:
        roteiro_path = Path(args.roteiro)
        if not roteiro_path.exists():
            print(f"Erro: roteiro nao encontrado: {roteiro_path}", file=sys.stderr)
            sys.exit(1)
        script_text = roteiro_path.read_text(encoding="utf-8").strip()
    else:
        roteiro_path = ROOT_DIR / "roteiro.txt"
        if not roteiro_path.exists():
            print(f"Erro: roteiro nao encontrado: {roteiro_path}", file=sys.stderr)
            print("Dica: forneca um arquivo de roteiro ou use --topic \"Seu Tema\" para producao automatica.")
            sys.exit(1)
        script_text = roteiro_path.read_text(encoding="utf-8").strip()

    if not script_text:
        print("Erro: roteiro vazio.", file=sys.stderr)
        sys.exit(1)

    # ── Carrega config ────────────────────────────────────────────────────────
    cfg = get_config(
        AGENT_DIR / "config.yaml",
        {"voice": args.voice, "whisper_model": args.whisper_model,
         "tts_engine": args.tts_engine}
    )
    _VERBOSE = cfg["agent"]["verbose"]

    # ── Voice Memory (recupera preferências salvas de voz, pitch, rate) ───────
    if _VOICE_MEM_AVAILABLE:
        try:
            vmem = _VMEM(AGENT_DIR / "memory")
            cfg = vmem.apply_to_cfg(cfg, cli_voice=args.voice, cli_engine=args.tts_engine)
            log(f"  [VoiceMemory] Preferencias carregadas: {vmem.log_summary()}")
        except Exception as e:
            log(f"  [VoiceMemory] Falha ao carregar preferencias: {e}", warn=True)

    # ── Carrega perfil de canal (se fornecido via --canal / --channel) ────────
    if getattr(args, "canal", None):
        canal_name = args.canal.lower().strip()
        candidates = [
            AGENT_DIR / "channels" / f"{canal_name}.yaml",
            AGENT_DIR / "channels" / f"{canal_name}s.yaml",
            AGENT_DIR / "channels" / f"{canal_name.rstrip('s')}.yaml",
        ]
        canal_yaml = next((p for p in candidates if p.exists()), None)
        if canal_yaml:
            try:
                canal_cfg = load_config(canal_yaml)
                # Merge: valores do canal sobrepõem config base
                for section, vals in canal_cfg.items():
                    if isinstance(vals, dict):
                        cfg.setdefault(section, {}).update(vals)
                    else:
                        cfg[section] = vals
                log(f"  Canal carregado: {canal_yaml.stem}")
            except Exception as e:
                log(f"  [WARN] Falha ao carregar canal '{canal_name}': {e}", warn=True)
        else:
            log(f"  [WARN] Canal '{canal_name}' nao encontrado em channels/. Usando config padrao.", warn=True)

    # ── Aplica API keys de linha de comando na config de media ────────────────
    if getattr(args, "pexels_key", None):
        cfg.setdefault("media", {})["pexels_api_key"] = args.pexels_key
    if getattr(args, "unsplash_key", None):
        cfg.setdefault("media", {})["unsplash_api_key"] = args.unsplash_key


    # ── Caminhos fixos ────────────────────────────────────────────────────────
    ffmpeg_path   = str(ROOT_DIR / "ffmpeg.exe") \
                    if (ROOT_DIR / "ffmpeg.exe").exists() \
                    else (shutil.which("ffmpeg") or "ffmpeg")
    audio_path    = str(ROOT_DIR / "narracao.mp3")
    srt_path      = str(ROOT_DIR / "narracao.srt")
    manifest_path = str(ROOT_DIR / "concat_list.txt")
    saida_dir     = ROOT_DIR / "saida"
    temp_clips    = str(ROOT_DIR / "temp_clips")
    checkpoint    = AGENT_DIR / "memory" / "last_run.json"
    plan_path     = ROOT_DIR / "ckpts" / "scenes_planned.json"

    for d in [saida_dir, ROOT_DIR / "ckpts", ROOT_DIR / "temp_clips",
              ROOT_DIR / "videos", ROOT_DIR / "imagens"]:
        d.mkdir(parents=True, exist_ok=True)

    out_video = str(saida_dir / cfg["output"]["video_filename"])
    out_thumb = str(saida_dir / cfg["output"]["thumbnail_filename"])

    # ── Checkpoint / resume ───────────────────────────────────────────────────
    state = {}
    if args.resume and not args.no_checkpoint:
        state = load_checkpoint(checkpoint)
        if state:
            log("Retomando do checkpoint salvo...")

    t0 = time.time()
    print("\n" + "="*62)
    print("  VideoFactoryAI — Pipeline Automatico de Producao de Videos")
    print("="*62)
    print(f"  Roteiro : {roteiro_path.name} ({len(script_text.split())} palavras)")
    print(f"  Saida   : {out_video}")
    print("="*62 + "\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1 — Planejamento de Cenas
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[1/10] Planejamento de cenas...")
    if state.get("scenes"):
        scenes = state["scenes"]
        log(f"  Cenas carregadas do checkpoint: {len(scenes)} cenas")
    else:
        scenes = plan_scenes(script_text, cfg)
        log(f"  {len(scenes)} cenas planejadas "
            f"({sum(1 for s in scenes if s['tipo']=='video')} video | "
            f"{sum(1 for s in scenes if s['tipo']=='image')} imagem)")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        if not args.no_checkpoint:
            state["scenes"] = scenes
            save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 2 — Geração de Voz
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[2/10] Geracao de voz (TTS)...")
    audio_path = generate_voice(script_text, audio_path, cfg)
    audio_dur  = get_audio_duration_simple(ffmpeg_path, audio_path)
    log(f"  Duracao do audio: {audio_dur:.1f}s ({audio_dur/60:.2f} min)")

    # Persiste configuração de voz utilizada para execuções futuras
    if _VOICE_MEM_AVAILABLE:
        try:
            vmem = _VMEM(AGENT_DIR / "memory")
            vmem.save(
                voice=cfg["tts"]["voice"],
                rate=cfg["tts"].get("rate", "+0%"),
                pitch=cfg["tts"].get("pitch", "+0Hz"),
                engine=cfg["tts"].get("engine", "edge-tts")
            )
            log("  [VoiceMemory] Preferencias de voz persistidas em memory/preferences.json")
        except Exception as e:
            log(f"  [VoiceMemory] Falha ao persistir: {e}", warn=True)
    if not args.no_checkpoint:
        state["audio_path"] = audio_path
        state["audio_dur"]  = audio_dur
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 3 — Geração de Legendas (Whisper)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[3/10] Geracao de legendas (Whisper)...")
    srt_blocks = generate_subtitles(audio_path, srt_path, cfg)
    scenes     = resync_scenes(scenes, srt_blocks, audio_dur)
    log(f"  Timecodes ressincronizados para {len(scenes)} cenas")
    if not args.no_checkpoint:
        state["scenes"]     = scenes
        state["srt_path"]   = srt_path
        state["srt_blocks"] = srt_blocks
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 4 — Busca de Mídia (hierarquia L1→L4)
    # MediaResearchAgent: L1 video real → L2 imagem real → L3 IA publica → L4 IA gerada
    # Fallback: source_media() legado (modules/media_engine.py)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[4/10] Busca de midia (L1 video real → L2 imagem → L3 IA publica → L4 IA gerada)...")
    compliance = None
    if _MRA_AVAILABLE:
        try:
            mra = _MRA(cfg, ROOT_DIR, AGENT_DIR / "memory")
            asset_map = mra.source_all(scenes)
            compliance = mra.compliance_summary()
            log(f"  {compliance['compliant']}/{compliance['total_assets']} assets com licenca verificada")
            log(f"  Distribuicao: {compliance.get('by_level', {})}")
        except Exception as e:
            log(f"  [WARN] MediaResearchAgent falhou ({e}). Usando source_media() legado.", warn=True)
            asset_map = source_media(scenes, cfg, ROOT_DIR)
    else:
        log("  [INFO] MediaResearchAgent nao disponivel. Usando source_media() legado.")
        asset_map = source_media(scenes, cfg, ROOT_DIR)
    log(f"  {len(asset_map)}/{len(scenes)} assets prontos")
    if not args.no_checkpoint:
        state["asset_map"] = {str(k): v for k, v in asset_map.items()}
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5 — Processamento Visual
    # (reutiliza modules/visual_processor.py diretamente)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[5/10] Processamento visual (Ken Burns + normalizacao 1080p)...")
    clips = process_all_scenes(scenes, asset_map, temp_clips, ffmpeg_path)
    log(f"  {len(clips)} clipes processados em temp_clips/")
    if not args.no_checkpoint:
        state["clips"] = clips
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 6 — Renderização Final
    # (reutiliza modules/composer.py diretamente)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[6/10] Renderizacao final (FFmpeg concat + audio + legendas)...")
    ok = assemble_master_documentary(
        clips, audio_path, srt_path, out_video, ffmpeg_path, manifest_path
    )
    if not ok:
        print("ERRO: renderizacao falhou.", file=sys.stderr)
        sys.exit(1)
    size_mb = os.path.getsize(out_video) / (1024*1024)
    log(f"  Video gerado: {Path(out_video).name} ({size_mb:.1f} MB)")
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 7 — Thumbnails Múltiplas e Contraste (ThumbnailAgent)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[7/10] Geracao de thumbnail (ThumbnailAgent: v1, v2, v3 + contraste)...")
    title_text   = roteiro_path.stem.replace("_", " ").title()
    canal_active = getattr(args, "canal", None)
    if _THUMB_AGENT_AVAILABLE:
        try:
            thumb_agent = _THUMBA(
                ffmpeg_path,
                saida_dir,
                cfg["output"]["thumbnail_width"],
                cfg["output"]["thumbnail_height"]
            )
            out_thumb = thumb_agent.run(
                video_path=out_video,
                asset_map=asset_map,
                scenes=scenes,
                title=title_text,
                canal=canal_active
            )
        except Exception as e:
            log(f"  [WARN] ThumbnailAgent falhou ({e}). Usando fallback simples.", warn=True)
            first_asset = asset_map.get(scenes[0]["id"], "") if scenes else ""
            generate_thumbnail(first_asset, out_thumb, title_text,
                               cfg["output"]["thumbnail_width"],
                               cfg["output"]["thumbnail_height"])
    else:
        first_asset = asset_map.get(scenes[0]["id"], "") if scenes else ""
        generate_thumbnail(first_asset, out_thumb, title_text,
                           cfg["output"]["thumbnail_width"],
                           cfg["output"]["thumbnail_height"])
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 8 — Controle de Qualidade (QualityAgent)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[8/10] Verificacao de qualidade (QualityAgent)...")
    if _QUALITY_AVAILABLE:
        try:
            qa = _QA(ffmpeg_path, saida_dir)
            passed = qa.run(
                video_path=out_video,
                audio_path=audio_path,
                srt_path=srt_path,
                asset_map=asset_map,
                scenes=scenes,
                expected_duration_s=audio_dur,
            )
            if not passed:
                print("\n" + "!"*62, file=sys.stderr)
                print("  ERRO CRITICO: QualityAgent reprovou o video final!", file=sys.stderr)
                print(f"  Consulte o relatorio em: {saida_dir / 'quality_report.json'}", file=sys.stderr)
                print("!"*62 + "\n", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            log(f"  [WARN] QualityAgent encontrou erro na verificacao: {e}", warn=True)
    else:
        log("  [INFO] QualityAgent nao disponivel. Pulando.")
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 9 — Metadados YouTube (SeoAgent)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[9/10] Geracao de metadados YouTube (SeoAgent)...")
    if _SEO_AVAILABLE:
        try:
            seo = _SEO(saida_dir)
            seo.run(
                script_text=script_text,
                scenes=scenes,
                audio_duration_s=audio_dur,
                roteiro_name=roteiro_path.stem,
                canal=canal_active
            )
        except Exception as e:
            log(f"  [WARN] SeoAgent encontrou erro: {e}", warn=True)
    else:
        log("  [INFO] SeoAgent nao disponivel.")
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 10 — Registro de Analytics (Analytics)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[10/10] Registro de analytics (Analytics)...")
    elapsed = time.time() - t0
    if _ANALYTICS_AVAILABLE:
        try:
            analytics = _ANALYTICS(AGENT_DIR / "memory")
            analytics.record(
                roteiro_name=roteiro_path.stem,
                scenes=scenes,
                asset_map=asset_map,
                audio_duration_s=audio_dur,
                elapsed_s=elapsed,
                canal=canal_active,
                compliance=compliance,
                output_video=out_video
            )
        except Exception as e:
            log(f"  [WARN] Analytics encontrou erro: {e}", warn=True)
    else:
        log("  [INFO] Analytics nao disponivel.")
    print("  [OK]\n")

    # ── Resumo Final ──────────────────────────────────────────────────────────
    m, s = divmod(int(elapsed), 60)
    if not args.no_checkpoint:
        state["output_video"] = out_video
        state["thumbnail"]    = out_thumb
        save_checkpoint(state, checkpoint)

    print("="*62)
    print("  PIPELINE CONCLUIDO COM SUCESSO!")
    print("="*62)
    print(f"  Tempo total    : {m}m {s}s")
    print(f"  Video final    : {out_video}")
    print(f"  Thumbnail      : {out_thumb}")
    print(f"  Qualidade      : {saida_dir / 'quality_report.json'}")
    print(f"  SEO / YouTube  : {saida_dir / 'youtube_metadata.json'}")
    print(f"  Historico      : {AGENT_DIR / 'memory' / 'project_history.json'}")
    print(f"  Cenas          : {len(scenes)}")
    print(f"  Duracao        : {audio_dur:.1f}s ({audio_dur/60:.2f} min)")
    print("="*62 + "\n")


if __name__ == "__main__":
    main()
